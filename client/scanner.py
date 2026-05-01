from __future__ import annotations

from pathlib import Path

from client.providers.base import RecordingProvider
from client.providers.generic_provider import GenericRecordingProvider
from client.providers.mcap_provider import McapRecordingProvider
from shared.models import RecordingMetadata


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: list[RecordingProvider] = []

    def register(self, provider: RecordingProvider) -> None:
        self._providers.append(provider)

    def get_provider(self, folder_path: Path) -> RecordingProvider:
        for p in self._providers:
            if p.can_handle(folder_path):
                return p
        raise ValueError(f"No provider can handle {folder_path}")


def build_default_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(McapRecordingProvider())
    registry.register(GenericRecordingProvider())
    return registry


def scan_recordings(storage_path: Path, registry: ProviderRegistry) -> list[RecordingMetadata]:
    if not storage_path.exists():
        raise FileNotFoundError(f"Storage path does not exist: {storage_path}")

    results: list[RecordingMetadata] = []
    for entry in sorted(storage_path.iterdir()):
        if entry.is_dir():
            provider = registry.get_provider(entry)
            results.append(provider.extract_metadata(entry))
    return results
