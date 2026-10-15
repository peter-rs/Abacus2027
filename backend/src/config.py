"""
Process-environment accessors shared by the backend.
"""

import os
from typing import Optional
from urllib.parse import quote_plus


def optional_env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = (os.environ.get(name) or "").strip()
    return value if value else default


def require_env(name: str) -> str:
    value = optional_env(name)
    if value is None:
        raise RuntimeError(f"{name} is not set.")
    return value


def _to_int(name: str, value: str) -> int:
    try:
        return int(value)
    except ValueError as e:
        raise RuntimeError(f"{name} must be an integer.") from e


def require_int_env(name: str) -> int:
    return _to_int(name, require_env(name))


def optional_int_env(name: str, default: int) -> int:
    value = optional_env(name)
    return default if value is None else _to_int(name, value)


def env_bool(name: str, default: bool = False) -> bool:
    value = optional_env(name)
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "y", "on")


def env_list(name: str, default: Optional[list[str]] = None) -> list[str]:
    """Comma-separated list. Blank items are dropped."""
    value = optional_env(name)
    if value is None:
        return list(default or [])
    return [item.strip() for item in value.split(",") if item.strip()]


def database_uri() -> str:
    """
    Builds the SQLAlchemy URI from DB_USER, DB_PASSWORD, DB_HOST, DB_NAME and
    optional DB_PORT (default 3306). Credentials are URL-escaped so passwords
    containing '@', '/', or ':' do not corrupt the URI.
    """
    user = require_env("DB_USER")
    password = require_env("DB_PASSWORD")
    host = require_env("DB_HOST")
    name = require_env("DB_NAME")
    port = optional_int_env("DB_PORT", 3306)
    return f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{name}"
