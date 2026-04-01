"""Content and ContentVariant models."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class ContentStatus(str, enum.Enum):
    GENERATING = "GENERATING"
    PENDING_REVIEW = "PENDING_REVIEW"
    READY = "READY"
    POSTED = "POSTED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class Content(Base):
    __tablename__ = "content"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(64), index=True)
    niche: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(512))
    hook: Mapped[str] = mapped_column(Text, default="")
    script: Mapped[str] = mapped_column(Text, default="")
    scene_descriptions: Mapped[str] = mapped_column(Text, default="")  # JSON list
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus), default=ContentStatus.GENERATING, index=True
    )
    master_video_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    variants: Mapped[list[ContentVariant]] = relationship(
        "ContentVariant", back_populates="content", cascade="all, delete-orphan"
    )


class ContentVariant(Base):
    __tablename__ = "content_variant"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_id: Mapped[int] = mapped_column(Integer, ForeignKey("content.id"), index=True)
    platform: Mapped[str] = mapped_column(String(32))  # facebook, instagram, youtube, tiktok
    video_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    caption: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[str] = mapped_column(Text, default="")  # JSON list
    cta: Mapped[str] = mapped_column(String(512), default="")
    speed_factor: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    content: Mapped[Content] = relationship("Content", back_populates="variants")
