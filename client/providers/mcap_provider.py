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


class _McapSummary:
    start_time: datetime | None = None
    duration_seconds: float | None = None
    topic_count: int = 0
    message_count: int = 0


def _read_mcap_summary(folder_path: Path) -> _McapSummary:
    result = _McapSummary()
    try:
        from mcap.reader import make_reader  # type: ignore[import]
    except ImportError:
        return result

    earliest_ns: int | None = None
    latest_ns: int | None = None
    total_messages = 0
    topics: set[str] = set()

    for mcap_file in folder_path.rglob("*.mcap"):
        try:
            with open(mcap_file, "rb") as f:
                reader = make_reader(f)
                summary = reader.get_summary()
                if not summary or not summary.statistics:
                    continue
                stats = summary.statistics
                if stats.message_start_time:
                    if earliest_ns is None or stats.message_start_time < earliest_ns:
                        earliest_ns = stats.message_start_time
                if stats.message_end_time:
                    if latest_ns is None or stats.message_end_time > latest_ns:
                        latest_ns = stats.message_end_time
                total_messages += stats.message_count
                for ch in (summary.channels or {}).values():
                    topics.add(ch.topic)
        except Exception:
            pass

    if earliest_ns is not None:
        result.start_time = datetime.fromtimestamp(earliest_ns / 1e9, tz=timezone.utc)
    if earliest_ns is not None and latest_ns is not None and latest_ns > earliest_ns:
        result.duration_seconds = (latest_ns - earliest_ns) / 1e9
    result.message_count = total_messages
    result.topic_count = len(topics)
    return result


class McapRecordingMetadata(RecordingMetadata):
    topic_count: int = 0
    message_count: int = 0


class McapRecordingProvider(RecordingProvider):
    def can_handle(self, folder_path: Path) -> bool:
        return any(folder_path.rglob("*.mcap"))

    def extract_metadata(self, folder_path: Path) -> McapRecordingMetadata:
        parsed = _parse_folder_name(folder_path)
        robot_name = parsed[0] if parsed else folder_path.name
        folder_start = parsed[1] if parsed else datetime.fromtimestamp(
            folder_path.stat().st_mtime, tz=timezone.utc
        )

        mcap = _read_mcap_summary(folder_path)

        return McapRecordingMetadata(
            name=folder_path.name,
            robot_name=robot_name,
            start_time=mcap.start_time or folder_start,
            duration_seconds=mcap.duration_seconds,
            size_bytes=_folder_size(folder_path),
            topic_count=mcap.topic_count,
            message_count=mcap.message_count,
        )
