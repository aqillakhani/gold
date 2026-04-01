"""Meta Platform adapter — Facebook Pages + Instagram Reels via Graph API."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

from ..config import Config
from ..utils.retry import retry
from .base import PlatformAdapter

logger = logging.getLogger(__name__)

GRAPH_API = "https://graph.facebook.com"
INSTAGRAM_API = "https://graph.instagram.com"


class FacebookAdapter(PlatformAdapter):
    platform_name = "facebook"

    def __init__(self, config: Config, account_id: str):
        self.config = config
        self.account_id = account_id
        self._load_credentials()

    def _load_credentials(self) -> None:
        accounts = self.config.accounts.get("accounts", [])
        acct = next((a for a in accounts if a["id"] == self.account_id), None)
        if not acct:
            raise ValueError(f"Account {self.account_id} not found")
        fb = acct["platforms"]["facebook"]
        self.page_id = fb["page_id"]
        self.access_token = self.config.env(fb["token_env"])
        self.api_version = self.config.get("platforms.facebook.api_version", "v19.0")

    @retry(max_retries=3, base_delay=5.0, exceptions=(httpx.HTTPError,))
    async def post(
        self,
        video_path: Path,
        caption: str,
        hashtags: list[str],
        thumbnail_path: Path | None = None,
    ) -> dict:
        full_caption = f"{caption}\n\n{' '.join(hashtags)}"

        async with httpx.AsyncClient(timeout=300) as client:
            # Upload video via resumable upload
            # Step 1: Start upload
            start_resp = await client.post(
                f"{GRAPH_API}/{self.api_version}/{self.page_id}/videos",
                data={
                    "access_token": self.access_token,
                    "upload_phase": "start",
                    "file_size": str(video_path.stat().st_size),
                },
            )
            start_resp.raise_for_status()
            upload_data = start_resp.json()
            upload_session_id = upload_data["upload_session_id"]
            video_id = upload_data.get("video_id")

            # Step 2: Transfer
            with open(video_path, "rb") as f:
                transfer_resp = await client.post(
                    f"{GRAPH_API}/{self.api_version}/{self.page_id}/videos",
                    data={
                        "access_token": self.access_token,
                        "upload_phase": "transfer",
                        "upload_session_id": upload_session_id,
                        "start_offset": "0",
                    },
                    files={"video_file_chunk": f},
                )
                transfer_resp.raise_for_status()

            # Step 3: Finish
            finish_resp = await client.post(
                f"{GRAPH_API}/{self.api_version}/{self.page_id}/videos",
                data={
                    "access_token": self.access_token,
                    "upload_phase": "finish",
                    "upload_session_id": upload_session_id,
                    "description": full_caption,
                    "published": "true",
                },
            )
            finish_resp.raise_for_status()
            result = finish_resp.json()

        post_id = result.get("id") or video_id
        logger.info("[FB] Posted video %s for %s", post_id, self.account_id)
        return {"post_id": post_id, "platform": "facebook", "response": result}

    async def refresh_auth(self) -> None:
        """Facebook long-lived tokens last 60 days. Exchange before expiry."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{GRAPH_API}/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": self.config.env("META_APP_ID"),
                    "client_secret": self.config.env("META_APP_SECRET"),
                    "fb_exchange_token": self.access_token,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            new_token = data.get("access_token")
            if new_token:
                self.access_token = new_token
                logger.info("[FB] Token refreshed for %s", self.account_id)

    async def get_metrics(self, post_id: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{GRAPH_API}/{self.api_version}/{post_id}",
                params={
                    "access_token": self.access_token,
                    "fields": "views,likes.summary(true),comments.summary(true),shares",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return {
            "views": data.get("views", 0),
            "likes": data.get("likes", {}).get("summary", {}).get("total_count", 0),
            "comments": data.get("comments", {}).get("summary", {}).get("total_count", 0),
            "shares": data.get("shares", {}).get("count", 0),
        }

    async def post_comment(self, post_id: str, message: str) -> str | None:
        """Post a comment on a Facebook video (for auto-pin engagement)."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{GRAPH_API}/{self.api_version}/{post_id}/comments",
                    data={
                        "access_token": self.access_token,
                        "message": message,
                    },
                )
                resp.raise_for_status()
                comment_id = resp.json().get("id")
                logger.info("[FB] Posted comment %s on %s", comment_id, post_id)
                return comment_id
        except Exception as e:
            logger.warning("[FB] Comment failed on %s: %s", post_id, e)
            return None

    async def check_rate_limit(self) -> bool:
        return True  # 200 calls/hr is generous


class InstagramAdapter(PlatformAdapter):
    platform_name = "instagram"

    def __init__(self, config: Config, account_id: str):
        self.config = config
        self.account_id = account_id
        self._load_credentials()

    def _load_credentials(self) -> None:
        accounts = self.config.accounts.get("accounts", [])
        acct = next((a for a in accounts if a["id"] == self.account_id), None)
        if not acct:
            raise ValueError(f"Account {self.account_id} not found")
        ig = acct["platforms"]["instagram"]
        self.ig_account_id = ig["account_id"]
        self.access_token = self.config.env(ig["token_env"])
        self.api_version = self.config.get("platforms.instagram.api_version", "v19.0")

    @retry(max_retries=3, base_delay=5.0, exceptions=(httpx.HTTPError,))
    async def post(
        self,
        video_path: Path,
        caption: str,
        hashtags: list[str],
        thumbnail_path: Path | None = None,
    ) -> dict:
        """Post an IG Reel. Requires video at a public URL."""
        full_caption = f"{caption}\n\n{' '.join(hashtags)}"

        # IG requires a public URL for the video
        video_url = await self._upload_to_temp_host(video_path)

        async with httpx.AsyncClient(timeout=300) as client:
            # Step 1: Create media container (Instagram API)
            create_resp = await client.post(
                f"{INSTAGRAM_API}/{self.api_version}/{self.ig_account_id}/media",
                data={
                    "access_token": self.access_token,
                    "media_type": "REELS",
                    "video_url": video_url,
                    "caption": full_caption,
                },
            )
            create_resp.raise_for_status()
            container_id = create_resp.json()["id"]

            # Step 2: Wait for processing, then publish
            for _ in range(60):  # max 5 minutes
                status_resp = await client.get(
                    f"{INSTAGRAM_API}/{self.api_version}/{container_id}",
                    params={
                        "access_token": self.access_token,
                        "fields": "status_code",
                    },
                )
                status = status_resp.json().get("status_code")
                if status == "FINISHED":
                    break
                if status == "ERROR":
                    raise RuntimeError(f"IG media processing failed: {status_resp.json()}")
                await asyncio.sleep(5)

            # Step 3: Publish
            publish_resp = await client.post(
                f"{INSTAGRAM_API}/{self.api_version}/{self.ig_account_id}/media_publish",
                data={
                    "access_token": self.access_token,
                    "creation_id": container_id,
                },
            )
            publish_resp.raise_for_status()
            result = publish_resp.json()

        post_id = result.get("id")
        logger.info("[IG] Posted Reel %s for %s", post_id, self.account_id)
        return {"post_id": post_id, "platform": "instagram", "response": result}

    async def _upload_to_temp_host(self, video_path: Path) -> str:
        """Upload video to S3 and return a presigned URL for Instagram."""
        from ..utils.s3_uploader import S3Uploader

        uploader = S3Uploader(self.config)
        url = await asyncio.to_thread(
            uploader.upload_and_get_url, video_path, prefix="instagram", expiry=3600
        )
        logger.info("[IG] Video uploaded to S3, presigned URL ready")
        return url

    async def refresh_auth(self) -> None:
        pass

    async def get_metrics(self, post_id: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{GRAPH_API}/{self.api_version}/{post_id}/insights",
                params={
                    "access_token": self.access_token,
                    "metric": "plays,likes,comments,shares",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        metrics = {}
        for item in data.get("data", []):
            metrics[item["name"]] = item.get("values", [{}])[0].get("value", 0)
        return metrics

    async def post_comment(self, post_id: str, message: str) -> str | None:
        """Post a comment on an Instagram Reel."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{GRAPH_API}/{self.api_version}/{post_id}/comments",
                    data={
                        "access_token": self.access_token,
                        "message": message,
                    },
                )
                resp.raise_for_status()
                comment_id = resp.json().get("id")
                logger.info("[IG] Posted comment %s on %s", comment_id, post_id)
                return comment_id
        except Exception as e:
            logger.warning("[IG] Comment failed on %s: %s", post_id, e)
            return None

    async def check_rate_limit(self) -> bool:
        return True
