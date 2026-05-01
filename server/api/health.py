from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from server import crud
from server.database import get_db

router = APIRouter()


@router.get("/health")
def health(db: Session = Depends(get_db)):
    return {"status": "ok", "recording_count": crud.count_recordings(db)}
