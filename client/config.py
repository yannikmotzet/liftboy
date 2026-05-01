from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]

_DEFAULT_CONFIG_PATH = Path.home() / ".config" / "liftboy" / "client.toml"


@dataclass
class ClientConfig:
    server_url: str = "http://localhost:8000"
    storage_path: Path = field(default_factory=lambda: Path("/data/recordings"))
    network_path: Path = field(default_factory=lambda: Path("/mnt/nas/recordings"))
    delete_after_upload: bool = True
    rsync_bwlimit: int = 0  # KB/s, 0 = unlimited


def load_client_config() -> ClientConfig:
    config_path = Path(os.environ.get("LIFTBOY_CLIENT_CONFIG", _DEFAULT_CONFIG_PATH))
    cfg = ClientConfig()

    if config_path.exists():
        with open(config_path, "rb") as f:
            raw = tomllib.load(f)
        data = raw.get("liftboy", {})
        cfg.server_url = data.get("server_url", cfg.server_url)
        cfg.storage_path = Path(data.get("storage_path", cfg.storage_path))
        cfg.network_path = Path(data.get("network_path", cfg.network_path))
        cfg.delete_after_upload = data.get("delete_after_upload", cfg.delete_after_upload)
        rsync = raw.get("rsync", {})
        cfg.rsync_bwlimit = int(rsync.get("bwlimit", cfg.rsync_bwlimit))

    cfg.server_url = os.environ.get("LIFTBOY_SERVER_URL", cfg.server_url)
    if v := os.environ.get("LIFTBOY_STORAGE_PATH"):
        cfg.storage_path = Path(v)
    if v := os.environ.get("LIFTBOY_NETWORK_PATH"):
        cfg.network_path = Path(v)
    if v := os.environ.get("LIFTBOY_DELETE_AFTER_UPLOAD"):
        cfg.delete_after_upload = v.lower() not in ("0", "false", "no")

    return cfg
