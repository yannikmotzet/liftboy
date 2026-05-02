from __future__ import annotations

import logging
import shutil
import signal
import sys

from rich.console import Console
from rich.logging import RichHandler

from client.api_client import LiftboyApiClient
from client.config import load_client_config
from client.scanner import build_default_registry, scan_recordings
from client.tui import TuiManager
from client.uploader import RsyncUploader
from shared.models import RecordingResponse, RecordingStatus, UpdateProgressRequest, UpdateStatusRequest

# Single console shared with the TUI so log messages are buffered above the
# live display instead of being overwritten by the next redraw.
_console = Console()
logging.basicConfig(
    level=logging.WARNING,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=_console, show_path=False)],
)


def _fmt_size(b: int) -> str:
    if b >= 1_073_741_824:
        return f"{b / 1_073_741_824:.1f} GB"
    if b >= 1_048_576:
        return f"{b / 1_048_576:.1f} MB"
    return f"{b / 1024:.1f} KB"


def main() -> None:
    cfg = load_client_config()

    registry = build_default_registry()

    try:
        recordings = scan_recordings(cfg.storage_path, registry)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not recordings:
        print("No recordings found in", cfg.storage_path)
        sys.exit(0)

    print(f"Found {len(recordings)} recording(s) in {cfg.storage_path}")
    print(f"Server: {cfg.server_url}")
    print(f"Destination: {cfg.network_path}")
    print()

    api = LiftboyApiClient(cfg.server_url)

    # Register all recordings with the server
    server_recs: list[RecordingResponse | None] = []
    for rec in recordings:
        sr = api.register_recording(rec)
        server_recs.append(sr)
        status = "registered" if sr else "server unreachable"
        print(f"  {rec.name:60s} {_fmt_size(rec.size_bytes):>10s}  [{status}]")

    print()

    uploader = RsyncUploader(bwlimit=cfg.rsync_bwlimit)

    # Track which recording is currently uploading for interrupt handling
    current_server_rec: RecordingResponse | None = None

    def _handle_interrupt(signum: int, frame: object) -> None:
        if current_server_rec is not None:
            api.update_status(
                current_server_rec.id,
                UpdateStatusRequest(status=RecordingStatus.interrupted),
            )
        print("\nInterrupted. Uploading marked as interrupted on server.", file=sys.stderr)
        sys.exit(130)

    signal.signal(signal.SIGINT, _handle_interrupt)
    signal.signal(signal.SIGTERM, _handle_interrupt)

    with TuiManager(recordings, console=_console) as tui:
        for rec, server_rec in zip(recordings, server_recs):
            if server_rec is None:
                tui.update_row(rec.name, "failed", 0.0)
                continue

            current_server_rec = server_rec
            api.update_status(
                server_rec.id,
                UpdateStatusRequest(status=RecordingStatus.uploading),
            )
            tui.update_row(rec.name, "uploading", 0.0)

            def on_progress(
                pct: float,
                bytes_xfrd: int,
                eta_secs: float | None,
                speed_bps: float | None = None,
                _id: int = server_rec.id,
                _name: str = rec.name,
                _size: int = rec.size_bytes,
            ) -> None:
                api.update_progress(
                    _id,
                    UpdateProgressRequest(
                        progress_pct=pct,
                        bytes_transferred=bytes_xfrd,
                        eta_seconds=eta_secs,
                        speed_bytes_per_sec=speed_bps,
                    ),
                )
                tui.set_connection_status(api.connected)
                tui.update_row(_name, "uploading", pct, eta_secs, bytes_xfrd, _size, speed_bps)

            src = cfg.storage_path / rec.name
            dest = cfg.network_path / rec.name
            success = uploader.upload(src, dest, on_progress)

            if success:
                if cfg.delete_after_upload and src.exists():
                    shutil.rmtree(src)
                api.update_status(
                    server_rec.id,
                    UpdateStatusRequest(status=RecordingStatus.completed),
                )
                tui.update_row(rec.name, "completed", 100.0)
            else:
                api.update_status(
                    server_rec.id,
                    UpdateStatusRequest(status=RecordingStatus.failed),
                )
                tui.update_row(rec.name, "failed", 0.0)

            current_server_rec = None

    api.close()


if __name__ == "__main__":
    main()
