"""Account and credential management models."""

from __future__ import annotations

import os
from datetime import datetime

from cryptography.fernet import Fernet
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class PlatformConnection(Base):
    __tablename__ = "platform_connection"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(64), index=True)
    platform: Mapped[str] = mapped_column(String(32))
    encrypted_token: Mapped[str] = mapped_column(Text, default="")
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_data: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class CredentialManager:
    """Encrypts/decrypts tokens with Fernet."""

    def __init__(self, key: str | None = None):
        raw_key = key or os.environ.get("FERNET_KEY", "")
        if not raw_key:
            raw_key = Fernet.generate_key().decode()
            print(f"[WARN] No FERNET_KEY set. Generated ephemeral key: {raw_key}")
        if isinstance(raw_key, str):
            raw_key = raw_key.encode()
        self._fernet = Fernet(raw_key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()
