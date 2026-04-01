"""YouTube adapter — Shorts upload via Data API v3."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from ..config import Config
from ..utils.retry import retry
from .base import PlatformAdapter

logger = logging.getLogger(__name__)


class YouTubeAdapter(PlatformAdapter):
    platform_name = "youtube"

    def __init__(self, config: Config, account_id: str):
        self.config = config
        self.account_id = account_id
        self._load_credentials()

    def _load_credentials(self) -> None:
        accounts = self.config.accounts.get("accounts", [])
        acct = next((a for a in accounts if a["id"] == self.account_id), None)
        if not acct:
            raise ValueError(f"Account {self.account_id} not found")
        yt = acct["platforms"]["youtube"]
        self.channel_id = yt["channel_id"]
        self.client_id = self.config.env(yt["client_id_env"])
        self.client_secret = self.config.env(yt["client_secret_env"])
        self.refresh_token = self.config.env(yt["refresh_token_env"])

    def _get_credentials(self) -> Credentials:
        creds = Credentials(
            token=None,
            refresh_token=self.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
        )
        creds.refresh(Request())
        return creds

    @retry(max_retries=2, base_delay=10.0, exceptions=(Exception,))
    async def post(
        self,
        video_path: Path,
        caption: str,
        hashtags: list[str],
        thumbnail_path: Path | None = None,
    ) -> dict:
        """Upload a YouTube Short."""

        def _upload():
            creds = self._get_credentials()
            youtube = build("youtube", "v3", credentials=creds)

            title = caption[:100] if caption else "Short"
            description = f"{caption}\n\n{' '.join(hashtags)}"

            body = {
                "snippet": {
                    "title": title,
                    "description": description,
                    "tags": [h.lstrip("#") for h in hashtags[:15]],
                    "categoryId": "22",
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False,
                    "madeForKids": False,
                    "notifySubscribers": True,
                },
            }

            # AI disclosure: add label to description
            ai_disclosure = "\n\n---\nAI-generated content: voice, visuals, and script created with AI tools."
            if ai_disclosure not in description:
                body["snippet"]["description"] = description + ai_disclosure

            media = MediaFileUpload(
                str(video_path),
                mimetype="video/mp4",
                resumable=True,
                chunksize=10 * 1024 * 1024,
            )

            request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            response = None
            while response is None:
                _, response = request.next_chunk()

            video_id = response["id"]

            if thumbnail_path and thumbnail_path.exists():
                try:
                    youtube.thumbnails().set(
                        videoId=video_id,
                        media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/png"),
                    ).execute()
                except Exception as e:
                    logger.warning("[YT] Thumbnail upload failed: %s", e)

            return response

        result = await asyncio.to_thread(_upload)
        video_id = result["id"]
        logger.info("[YT] Uploaded Short %s for %s", video_id, self.account_id)
        return {"post_id": video_id, "platform": "youtube", "response": result}

    async def refresh_auth(self) -> None:
        pass

    async def get_metrics(self, post_id: str) -> dict:
        def _fetch():
            creds = self._get_credentials()
            youtube = build("youtube", "v3", credentials=creds)
            resp = youtube.videos().list(
                part="statistics",
                id=post_id,
            ).execute()
            items = resp.get("items", [])
            if not items:
                return {}
            stats = items[0].get("statistics", {})
            return {
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "shares": 0,
            }

        return await asyncio.to_thread(_fetch)

    async def post_comment(self, post_id: str, message: str) -> str | None:
        """Post and pin a comment on a YouTube video."""
        try:
            def _comment():
                creds = self._get_credentials()
                youtube = build("youtube", "v3", credentials=creds)
                # Insert comment
                resp = youtube.commentThreads().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "videoId": post_id,
                            "topLevelComment": {
                                "snippet": {"textOriginal": message}
                            },
                        }
                    },
                ).execute()
                comment_id = resp["id"]
                logger.info("[YT] Posted comment %s on %s", comment_id, post_id)
                return comment_id

            return await asyncio.to_thread(_comment)
        except Exception as e:
            logger.warning("[YT] Comment failed on %s: %s", post_id, e)
            return None

    async def check_rate_limit(self) -> bool:
        return True
