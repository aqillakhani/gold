"""Configuration loader for YAML settings and .env secrets."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


_ROOT = Path(__file__).resolve().parents[2]  # gold/ project root


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    """Loads and provides access to all configuration."""

    def __init__(self, root: Path | None = None):
        self.root = root or _ROOT
        self.config_dir = self.root / "config"
        self.secrets_dir = self.root / "secrets"
        self.data_dir = self.root / "data"

        # Load .env
        env_path = self.secrets_dir / ".env"
        if env_path.exists():
            load_dotenv(env_path)

        # Load settings
        self.settings: dict[str, Any] = self._load_yaml("settings.yaml")

        # Load accounts
        self.accounts: dict[str, Any] = self._load_yaml("accounts.yaml")

        # Load niche configs
        self.niches: dict[str, dict[str, Any]] = {}
        niches_dir = self.config_dir / "niches"
        if niches_dir.exists():
            for f in niches_dir.glob("*.yaml"):
                data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                niche_data = data.get("niche", data)
                niche_id = niche_data.get("id", f.stem)
                self.niches[niche_id] = niche_data

    def _load_yaml(self, filename: str) -> dict[str, Any]:
        path = self.config_dir / filename
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def get(self, dotpath: str, default: Any = None) -> Any:
        """Get a nested config value using dot notation: 'scheduling.posts_per_day_per_account'."""
        keys = dotpath.split(".")
        val: Any = self.settings
        for key in keys:
            if isinstance(val, dict):
                val = val.get(key)
            else:
                return default
            if val is None:
                return default
        return val

    def env(self, key: str, default: str = "") -> str:
        """Get an environment variable."""
        return os.environ.get(key, default)

    @property
    def db_url(self) -> str:
        db_path = self.data_dir / "gold.db"
        return f"sqlite+aiosqlite:///{db_path}"

    @property
    def db_url_sync(self) -> str:
        db_path = self.data_dir / "gold.db"
        return f"sqlite:///{db_path}"

    @property
    def dry_run(self) -> bool:
        return self.get("app.dry_run", False)

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"
