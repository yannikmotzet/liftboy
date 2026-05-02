from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class RecordingStatus(str, Enum):
    pending = "pending"
    uploading = "uploading"
    completed = "completed"
    failed = "failed"
    interrupted = "interrupted"


class RecordingMetadata(BaseModel):
    name: str
    robot_name: str
    start_time: datetime
    duration_seconds: float | None
    size_bytes: int


class RegisterRecordingRequest(BaseModel):
    name: str
    robot_name: str
    start_time: datetime
    duration_seconds: float | None = None
    size_bytes: int
    client_host: str | None = None


class UpdateProgressRequest(BaseModel):
    progress_pct: float
    bytes_transferred: int
    eta_seconds: float | None = None
    speed_bytes_per_sec: float | None = None


class UpdateStatusRequest(BaseModel):
    status: RecordingStatus
    error_message: str | None = None


class RecordingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    robot_name: str
    start_time: datetime
    duration_seconds: float | None
    size_bytes: int
    status: RecordingStatus
    progress_pct: float | None
    bytes_transferred: int | None
    eta_seconds: float | None
    registered_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    client_host: str | None
    error_message: str | None
    transfer_speed_bytes: float | None
