from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from server.models import Recording
from shared.models import (
    RecordingStatus,
    RegisterRecordingRequest,
    UpdateProgressRequest,
    UpdateStatusRequest,
)

VALID_TRANSITIONS: dict[str, set[str]] = {
    RecordingStatus.pending: {RecordingStatus.uploading},
    RecordingStatus.uploading: {
        RecordingStatus.completed,
        RecordingStatus.failed,
        RecordingStatus.interrupted,
    },
    RecordingStatus.interrupted: {RecordingStatus.uploading},
    RecordingStatus.failed: {RecordingStatus.uploading},
    RecordingStatus.completed: set(),
}


def create_or_get_recording(db: Session, req: RegisterRecordingRequest) -> Recording:
    existing = db.query(Recording).filter(Recording.name == req.name).first()
    if existing:
        if req.client_host and existing.client_host != req.client_host:
            existing.client_host = req.client_host
            existing.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(existing)
        return existing

    rec = Recording(
        name=req.name,
        robot_name=req.robot_name,
        start_time=req.start_time,
        duration_seconds=req.duration_seconds,
        size_bytes=req.size_bytes,
        status=RecordingStatus.pending,
        client_host=req.client_host,
        extra_metadata=req.extra_metadata,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def get_recording(db: Session, recording_id: int) -> Recording | None:
    return db.query(Recording).filter(Recording.id == recording_id).first()


def list_recordings(
    db: Session,
    robot_name: str | None = None,
    status: str | None = None,
    exclude_completed: bool = False,
) -> list[Recording]:
    q = db.query(Recording)
    if robot_name:
        q = q.filter(Recording.robot_name == robot_name)
    if exclude_completed:
        q = q.filter(Recording.status != RecordingStatus.completed)
    elif status:
        q = q.filter(Recording.status == status)
    return q.order_by(Recording.registered_at.desc()).all()


def update_progress(db: Session, recording_id: int, req: UpdateProgressRequest) -> Recording:
    rec = get_recording(db, recording_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recording not found")

    rec.progress_pct = req.progress_pct
    rec.bytes_transferred = req.bytes_transferred
    rec.eta_seconds = req.eta_seconds
    rec.transfer_speed_bytes = req.speed_bytes_per_sec
    rec.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rec)
    return rec


def update_status(db: Session, recording_id: int, req: UpdateStatusRequest) -> Recording:
    rec = get_recording(db, recording_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recording not found")

    allowed = VALID_TRANSITIONS.get(rec.status, set())
    if req.status not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot transition from '{rec.status}' to '{req.status}'",
        )

    rec.status = req.status
    rec.error_message = req.error_message
    rec.updated_at = datetime.now(timezone.utc)

    if req.status == RecordingStatus.completed:
        rec.completed_at = datetime.now(timezone.utc)
        rec.progress_pct = 100.0
        rec.eta_seconds = None
    elif req.status in (RecordingStatus.failed, RecordingStatus.interrupted):
        rec.eta_seconds = None

    db.commit()
    db.refresh(rec)
    return rec


def mark_stale_uploads_interrupted(db: Session, timeout_seconds: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
    stale = (
        db.query(Recording)
        .filter(Recording.status == RecordingStatus.uploading)
        .filter(Recording.updated_at < cutoff)
        .all()
    )
    for rec in stale:
        rec.status = RecordingStatus.interrupted
        rec.eta_seconds = None
        rec.error_message = f"No heartbeat for >{timeout_seconds}s — marked interrupted by server"
        rec.updated_at = datetime.now(timezone.utc)
    if stale:
        db.commit()
    return len(stale)


def get_client_summaries(db: Session) -> list[dict]:
    from collections import defaultdict

    # Fetch all non-terminal-failed recordings for active clients.
    # We need completed recordings too so progress doesn't reset between uploads.
    recs = (
        db.query(Recording)
        .filter(
            Recording.client_host.isnot(None),
            Recording.status.in_(["pending", "uploading", "interrupted", "completed"]),
        )
        .all()
    )

    # Only show a client card if it has at least one non-completed recording.
    active_clients: set[str] = set()
    for rec in recs:
        if rec.status != "completed":
            active_clients.add(rec.client_host)

    clients: dict[str, dict] = defaultdict(
        lambda: {"uploading": None, "pending": [], "interrupted": [], "completed_bytes": 0, "session_start": None}
    )
    for rec in recs:
        host = rec.client_host
        if host not in active_clients:
            continue
        if rec.status == "uploading":
            clients[host]["uploading"] = rec
        elif rec.status == "pending":
            clients[host]["pending"].append(rec)
        elif rec.status == "interrupted":
            clients[host]["interrupted"].append(rec)
        elif rec.status == "completed":
            clients[host]["completed_bytes"] += rec.size_bytes
        # Track earliest registration as session start
        ra = rec.registered_at
        prev = clients[host]["session_start"]
        if prev is None or ra < prev:
            clients[host]["session_start"] = ra

    result = []
    for client_id, data in clients.items():
        uploading = data["uploading"]
        pending_bytes = sum(r.size_bytes for r in data["pending"])
        completed_bytes = data["completed_bytes"]

        # Estimate total remaining time using current rsync transfer speed:
        # speed = remaining_active_bytes / active_eta_seconds
        # total_eta = active_eta + pending_bytes / speed
        total_eta = None
        if (
            uploading
            and uploading.eta_seconds is not None
            and uploading.progress_pct is not None
            and uploading.eta_seconds > 0
        ):
            remaining_active = uploading.size_bytes * (1 - uploading.progress_pct / 100)
            if remaining_active > 0:
                speed = remaining_active / uploading.eta_seconds
                total_eta = uploading.eta_seconds + pending_bytes / speed

        # Overall percentage across all bytes this client needs to transfer this session
        active_transferred = (uploading.bytes_transferred or 0) if uploading else 0
        total_bytes = (uploading.size_bytes if uploading else 0) + pending_bytes + completed_bytes
        transferred = active_transferred + completed_bytes
        overall_pct = transferred / total_bytes * 100 if total_bytes > 0 else 0.0

        # Wall-clock elapsed time since session start (monotonically increasing, no reset between recordings)
        session_start = data["session_start"]
        elapsed_seconds = None
        if session_start is not None:
            now = datetime.now(timezone.utc)
            ts = session_start if session_start.tzinfo else session_start.replace(tzinfo=timezone.utc)
            elapsed_seconds = (now - ts).total_seconds()

        result.append({
            "client_id": client_id,
            "uploading": uploading,
            "pending_count": len(data["pending"]),
            "pending_bytes": pending_bytes,
            "interrupted_count": len(data["interrupted"]),
            "total_eta_seconds": total_eta,
            "overall_pct": overall_pct,
            "elapsed_seconds": elapsed_seconds,
            "total_bytes": total_bytes,
            "transferred_bytes": transferred,
        })

    return sorted(result, key=lambda x: x["client_id"])


def count_recordings(db: Session) -> int:
    return db.query(Recording).count()
