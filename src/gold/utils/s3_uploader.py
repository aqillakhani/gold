"""S3 upload utility — generates presigned URLs for Instagram video hosting."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from ..config import Config

logger = logging.getLogger(__name__)


class S3Uploader:
    """Upload files to S3 and generate presigned URLs."""

    def __init__(self, config: Config):
        self.bucket = config.env("AWS_S3_BUCKET", "gold-video-uploads")
        self.region = config.env("AWS_S3_REGION", "us-east-1")
        self.client = boto3.client(
            "s3",
            aws_access_key_id=config.env("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=config.env("AWS_SECRET_ACCESS_KEY"),
            region_name=self.region,
        )

    def upload_and_get_url(
        self, file_path: Path, prefix: str = "instagram", expiry: int = 3600
    ) -> str:
        """Upload a file to S3 and return a presigned URL.

        Args:
            file_path: Local path to the video file.
            prefix: S3 key prefix (folder).
            expiry: URL expiry in seconds (default 1 hour).

        Returns:
            Presigned URL string.
        """
        key = f"{prefix}/{uuid.uuid4().hex}_{file_path.name}"

        try:
            self.client.upload_file(
                str(file_path),
                self.bucket,
                key,
                ExtraArgs={"ContentType": "video/mp4"},
            )
            logger.info("[S3] Uploaded %s -> s3://%s/%s", file_path.name, self.bucket, key)
        except ClientError as e:
            logger.error("[S3] Upload failed: %s", e)
            raise

        try:
            url = self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expiry,
            )
        except ClientError as e:
            logger.error("[S3] Presigned URL generation failed: %s", e)
            raise

        return url

    def cleanup(self, key: str) -> None:
        """Delete a file from S3 after posting."""
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            logger.info("[S3] Deleted s3://%s/%s", self.bucket, key)
        except ClientError as e:
            logger.warning("[S3] Cleanup failed: %s", e)
