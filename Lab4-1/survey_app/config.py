"""Project configuration. Secrets are loaded locally and excluded from repr/logs."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SEED = 20261015


def _dotenv_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(f".env line {number} has invalid assignment syntax")
        value = value.strip()
        if value.startswith(("'", '"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f".env line {number} has unmatched quotes")
            value = value[1:-1]
        values[key] = value
    return values


@dataclass(frozen=True)
class Settings:
    mongodb_uri: str = field(repr=False)
    database: str
    session_secret: str = field(repr=False)
    cookie_secure: bool = False
    session_ttl_seconds: int = 86400

    def __post_init__(self) -> None:
        if not isinstance(self.mongodb_uri, str) or not self.mongodb_uri.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError("MONGODB_URI must use the mongodb or mongodb+srv scheme")
        if not isinstance(self.database, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,63}", self.database):
            raise ValueError("MONGODB_DATABASE must contain 1–63 ASCII letters, digits, underscores or hyphens")
        if not isinstance(self.session_secret, str) or len(self.session_secret) < 32:
            raise ValueError("SESSION_SECRET must have at least 32 characters")
        if self.session_secret.startswith("replace-with-"):
            raise ValueError("SESSION_SECRET must replace the example placeholder")
        if type(self.cookie_secure) is not bool:
            raise ValueError("COOKIE_SECURE must be a boolean")
        if type(self.session_ttl_seconds) is not int or self.session_ttl_seconds <= 0:
            raise ValueError("SESSION_TTL_SECONDS must be a positive integer")

    @classmethod
    def from_env(cls) -> "Settings":
        values = _dotenv_values(PROJECT_ROOT / ".env")
        # Environment variables override the project-local file; neither is logged.
        for key in ("MONGODB_URI", "MONGODB_DATABASE", "SESSION_SECRET", "COOKIE_SECURE", "SESSION_TTL_SECONDS"):
            if key in os.environ:
                values[key] = os.environ[key]
        secure = values.get("COOKIE_SECURE", "false").strip().lower()
        if secure not in {"true", "false", "1", "0", "yes", "no"}:
            raise ValueError("COOKIE_SECURE must be true/false, 1/0 or yes/no")
        ttl = values.get("SESSION_TTL_SECONDS", "86400").strip()
        if not re.fullmatch(r"[0-9]+", ttl):
            raise ValueError("SESSION_TTL_SECONDS must be a positive integer")
        return cls(
            mongodb_uri=values.get("MONGODB_URI", ""),
            database=values.get("MONGODB_DATABASE", ""),
            session_secret=values.get("SESSION_SECRET", ""),
            cookie_secure=secure in {"true", "1", "yes"},
            session_ttl_seconds=int(ttl),
        )
