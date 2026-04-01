"""Fernet encryption utilities for token storage."""

from __future__ import annotations

from cryptography.fernet import Fernet


def generate_key() -> str:
    """Generate a new Fernet key."""
    return Fernet.generate_key().decode()


def encrypt_token(plaintext: str, key: str) -> str:
    f = Fernet(key.encode() if isinstance(key, str) else key)
    return f.encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str, key: str) -> str:
    f = Fernet(key.encode() if isinstance(key, str) else key)
    return f.decrypt(ciphertext.encode()).decode()
