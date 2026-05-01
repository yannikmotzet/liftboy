from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from shared.models import RecordingMetadata


class RecordingProvider(ABC):
    @abstractmethod
    def can_handle(self, folder_path: Path) -> bool:
        ...

    @abstractmethod
    def extract_metadata(self, folder_path: Path) -> RecordingMetadata:
        ...
