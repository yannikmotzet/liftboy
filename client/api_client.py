from __future__ import annotations

import logging
import time

import httpx

from shared.models import (
    RecordingMetadata,
    RecordingResponse,
    RegisterRecordingRequest,
    UpdateProgressRequest,
    UpdateStatusRequest,
)

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BACKOFF = 1.0


class LiftboyApiClient:
    def __init__(self, server_url: str) -> None:
        self._base = server_url.rstrip("/")
        self._client = httpx.Client(timeout=10.0)

    def _post(self, path: str, data: dict) -> httpx.Response | None:
        url = f"{self._base}{path}"
        for attempt in range(_MAX_RETRIES):
            try:
                resp = self._client.post(url, json=data)
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as e:
                logger.error("HTTP error %s: %s", e.response.status_code, e.response.text)
                return None
            except httpx.RequestError as e:
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_RETRY_BACKOFF * (2**attempt))
                else:
                    logger.warning("Server unreachable after %d retries: %s", _MAX_RETRIES, e)
        return None

    def _patch(self, path: str, data: dict) -> None:
        url = f"{self._base}{path}"
        for attempt in range(_MAX_RETRIES):
            try:
                resp = self._client.patch(url, json=data)
                resp.raise_for_status()
                return
            except httpx.HTTPStatusError as e:
                logger.error("HTTP error %s: %s", e.response.status_code, e.response.text)
                return
            except httpx.RequestError as e:
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_RETRY_BACKOFF * (2**attempt))
                else:
                    logger.warning("Server unreachable after %d retries: %s", _MAX_RETRIES, e)

    def register_recording(self, meta: RecordingMetadata) -> RecordingResponse | None:
        import os
        import socket

        try:
            hostname = socket.gethostname()
        except Exception:
            hostname = "unknown"
        try:
            import pwd
            username = pwd.getpwuid(os.getuid()).pw_name
        except Exception:
            username = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))
        host = f"{username}@{hostname}"

        req = RegisterRecordingRequest(
            name=meta.name,
            robot_name=meta.robot_name,
            start_time=meta.start_time,
            duration_seconds=meta.duration_seconds,
            size_bytes=meta.size_bytes,
            client_host=host,
        )
        resp = self._post("/recordings", req.model_dump(mode="json"))
        if resp is not None:
            return RecordingResponse.model_validate(resp.json())
        return None

    def update_progress(self, recording_id: int, req: UpdateProgressRequest) -> None:
        self._patch(f"/recordings/{recording_id}/progress", req.model_dump(mode="json"))

    def update_status(self, recording_id: int, req: UpdateStatusRequest) -> None:
        self._patch(f"/recordings/{recording_id}/status", req.model_dump(mode="json"))

    def close(self) -> None:
        self._client.close()
