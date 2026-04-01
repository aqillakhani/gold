"""TikTok adapter — Content Posting API v2."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

from ..config import Config
from ..utils.retry import retry
from .base import PlatformAdapter

logger = logging.getLogger(__name__)

TIKTOK_API = "https://open.tiktokapis.com/v2"


class TikTokAdapter(PlatformAdapter):
    platform_name = "tiktok"

    def __init__(self, config: Config, account_id: str):
        self.config = config
        self.account_id = account_id
        self._load_credentials()

    def _load_credentials(self) -> None:
        accounts = self.config.accounts.get("accounts", [])
        acct = next((a for a in accounts if a["id"] == self.account_id), None)
        if not acct:
            raise ValueError(f"Account {self.account_id} not found")
        tt = acct["platforms"]["tiktok"]
        self.access_token = self.config.env(tt["token_env"])

    @retry(max_retries=3, base_delay=10.0, exceptions=(httpx.HTTPError, RuntimeError))
    async def post(
        self,
        video_path: Path,
        caption: str,
        hashtags: list[str],
        thumbnail_path: Path | None = None,
    ) -> dict:
        """Upload video to TikTok via Content Posting API."""
        full_caption = f"{caption} {' '.join(hashtags)}"
        file_size = video_path.stat().st_size

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=300) as client:
            # Step 1: Initialize upload
            init_resp = await client.post(
                f"{TIKTOK_API}/post/publish/inbox/video/init/",
                headers=headers,
                json={
                    "post_info": {
                        "title": full_caption[:150],
                        "privacy_level": "PUBLIC_TO_EVERYONE",
                        "disable_duet": False,
                        "disable_comment": False,
                        "disable_stitch": False,
                        "is_aigc": True,
                    },
                    "source_info": {
                        "source": "FILE_UPLOAD",
                        "video_size": file_size,
                        "chunk_size": file_size,
                        "total_chunk_count": 1,
                    },
                },
            )
            init_resp.raise_for_status()
            init_data = init_resp.json()

            if init_data.get("error", {}).get("code") != "ok":
                raise RuntimeError(f"TikTok init failed: {init_data}")

            upload_url = init_data["data"]["upload_url"]
            publish_id = init_data["data"]["publish_id"]

            # Step 2: Upload video binary
            with open(video_path, "rb") as f:
                video_data = f.read()

            upload_resp = await client.put(
                upload_url,
                headers={
                    "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
                    "Content-Type": "video/mp4",
                },
                content=video_data,
            )
            upload_resp.raise_for_status()

            # Step 3: Check publish status
            status_data = {}
            for _ in range(60):
                status_resp = await client.post(
                    f"{TIKTOK_API}/post/publish/status/fetch/",
                    headers=headers,
                    json={"publish_id": publish_id},
                )
                status_resp.raise_for_status()
                status_data = status_resp.json()
                pub_status = status_data.get("data", {}).get("status")

                if pub_status == "PUBLISH_COMPLETE":
                    break
                if pub_status == "FAILED":
                    raise RuntimeError(f"TikTok publish failed: {status_data}")
                await asyncio.sleep(5)

        logger.info("[TT] Posted video %s for %s", publish_id, self.account_id)
        return {"post_id": publish_id, "platform": "tiktok", "response": status_data}

    async def refresh_auth(self) -> None:
        """Refresh TikTok OAuth2 token."""
        client_key = self.config.env("TIKTOK_CLIENT_KEY")
        client_secret = self.config.env("TIKTOK_CLIENT_SECRET")

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{TIKTOK_API}/oauth/token/",
                data={
                    "client_key": client_key,
                    "client_secret": client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": self.access_token,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("data", {}).get("access_token"):
                self.access_token = data["data"]["access_token"]
                logger.info("[TT] Token refreshed for %s", self.account_id)

    async def get_metrics(self, post_id: str) -> dict:
        return {"views": 0, "likes": 0, "comments": 0, "shares": 0}

    async def post_comment(self, post_id: str, message: str) -> str | None:
        """TikTok Content Posting API does not support comments. No-op."""
        logger.debug("[TT] Comment posting not supported via API for %s", post_id)
        return None

    async def check_rate_limit(self) -> bool:
        return True
