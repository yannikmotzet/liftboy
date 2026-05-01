from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from server import crud
from server.database import get_db
from shared.models import (
    RecordingResponse,
    RegisterRecordingRequest,
    UpdateProgressRequest,
    UpdateStatusRequest,
)

router = APIRouter()


@router.post("", response_model=RecordingResponse, status_code=201)
def register_recording(req: RegisterRecordingRequest, db: Session = Depends(get_db)):
    return crud.create_or_get_recording(db, req)


@router.get("", response_model=list[RecordingResponse])
def list_recordings(
    robot: str | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
):
    return crud.list_recordings(db, robot_name=robot, status=status)


@router.get("/{recording_id}", response_model=RecordingResponse)
def get_recording(recording_id: int, db: Session = Depends(get_db)):
    from fastapi import HTTPException

    rec = crud.get_recording(db, recording_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    return rec


@router.patch("/{recording_id}/progress", response_model=RecordingResponse)
def update_progress(
    recording_id: int, req: UpdateProgressRequest, db: Session = Depends(get_db)
):
    return crud.update_progress(db, recording_id, req)


@router.patch("/{recording_id}/status", response_model=RecordingResponse)
def update_status(recording_id: int, req: UpdateStatusRequest, db: Session = Depends(get_db)):
    return crud.update_status(db, recording_id, req)
