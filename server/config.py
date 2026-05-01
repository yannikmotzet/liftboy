from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]

_DEFAULT_CONFIG_PATH = Path.home() / ".config" / "liftboy" / "server.toml"


@dataclass
class ServerConfig:
    db_path: str = "./liftboy.db"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    upload_stale_timeout_seconds: int = 15


def load_server_config() -> ServerConfig:
    config_path = Path(os.environ.get("LIFTBOY_SERVER_CONFIG", _DEFAULT_CONFIG_PATH))
    cfg = ServerConfig()

    if config_path.exists():
        with open(config_path, "rb") as f:
            data = tomllib.load(f).get("liftboy", {})
        cfg.db_path = data.get("db_path", cfg.db_path)
        cfg.host = data.get("host", cfg.host)
        cfg.port = int(data.get("port", cfg.port))
        cfg.log_level = data.get("log_level", cfg.log_level)
        cfg.upload_stale_timeout_seconds = int(
            data.get("upload_stale_timeout_seconds", cfg.upload_stale_timeout_seconds)
        )

    cfg.db_path = os.environ.get("LIFTBOY_DB_PATH", cfg.db_path)
    cfg.host = os.environ.get("LIFTBOY_HOST", cfg.host)
    cfg.port = int(os.environ.get("LIFTBOY_PORT", cfg.port))
    if v := os.environ.get("LIFTBOY_UPLOAD_STALE_TIMEOUT_SECONDS"):
        cfg.upload_stale_timeout_seconds = int(v)

    return cfg
