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


class GenericRecordingProvider(RecordingProvider):
    def can_handle(self, folder_path: Path) -> bool:
        return True

    def extract_metadata(self, folder_path: Path) -> RecordingMetadata:
        m = _FOLDER_RE.match(folder_path.name)
        if m:
            robot_name = m.group("robot")
            date_str = m.group("date")
            time_str = m.group("time").replace("-", ":")
            try:
                start_time = datetime.fromisoformat(f"{date_str}T{time_str}").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                start_time = datetime.fromtimestamp(
                    folder_path.stat().st_mtime, tz=timezone.utc
                )
        else:
            robot_name = folder_path.name
            start_time = datetime.fromtimestamp(folder_path.stat().st_mtime, tz=timezone.utc)

        return RecordingMetadata(
            name=folder_path.name,
            robot_name=robot_name,
            start_time=start_time,
            duration_seconds=None,
            size_bytes=_folder_size(folder_path),
        )
