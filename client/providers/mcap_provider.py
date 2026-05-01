from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

from client.providers.base import RecordingProvider
from shared.models import RecordingMetadata

_FOLDER_RE = re.compile(
    r"^(?P<robot>.+)_(?P<date>\d{4}-\d{2}-\d{2})_(?P<time>\d{2}-\d{2}-\d{2})$"
)


def _folder_size(path: Path) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for fname in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, fname))
            except OSError:
                pass
    return total


def _parse_folder_name(folder_path: Path) -> tuple[str, datetime] | None:
    m = _FOLDER_RE.match(folder_path.name)
    if not m:
        return None
    robot = m.group("robot")
    date_str = m.group("date")
    time_str = m.group("time").replace("-", ":")
    try:
        start_time = datetime.fromisoformat(f"{date_str}T{time_str}").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None
    return robot, start_time


def _mcap_duration(folder_path: Path) -> float | None:
    try:
        from mcap.reader import make_reader  # type: ignore[import]
    except ImportError:
        return None

    total_ns = 0
    for mcap_file in folder_path.rglob("*.mcap"):
        try:
            with open(mcap_file, "rb") as f:
                reader = make_reader(f)
                stats = reader.get_summary()
                if stats and stats.statistics:
                    s = stats.statistics
                    if s.message_start_time and s.message_end_time:
                        total_ns += s.message_end_time - s.message_start_time
        except Exception:
            pass

    return total_ns / 1e9 if total_ns > 0 else None


class McapRecordingProvider(RecordingProvider):
    def can_handle(self, folder_path: Path) -> bool:
        return any(folder_path.rglob("*.mcap"))

    def extract_metadata(self, folder_path: Path) -> RecordingMetadata:
        parsed = _parse_folder_name(folder_path)
        if parsed:
            robot_name, start_time = parsed
        else:
            robot_name = folder_path.name
            start_time = datetime.fromtimestamp(folder_path.stat().st_mtime, tz=timezone.utc)

        return RecordingMetadata(
            name=folder_path.name,
            robot_name=robot_name,
            start_time=start_time,
            duration_seconds=_mcap_duration(folder_path),
            size_bytes=_folder_size(folder_path),
        )
