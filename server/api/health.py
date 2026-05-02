from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from server import crud
from server.database import get_db
from shared.models import RecordingResponse

router = APIRouter()


@router.get("/health")
def health(db: Session = Depends(get_db)):
    return {"status": "ok", "recording_count": crud.count_recordings(db)}


@router.get("/fleet")
def fleet(db: Session = Depends(get_db)):
    summaries = crud.get_client_summaries(db)
    result = []
    for s in summaries:
        uploading = s["uploading"]
        result.append({
            **{k: v for k, v in s.items() if k != "uploading"},
            "uploading": RecordingResponse.model_validate(uploading).model_dump(mode="json") if uploading else None,
        })
    return result
