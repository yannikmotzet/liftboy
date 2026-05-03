from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def init_db(db_path: str = "./liftboy.db") -> None:
    global _engine, _SessionLocal
    _engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    Base.metadata.create_all(bind=_engine)
    # migrate: add columns introduced after initial schema
    with _engine.connect() as conn:
        for col in ("transfer_speed_bytes REAL", "extra_metadata TEXT"):
            try:
                conn.execute(text(f"ALTER TABLE recordings ADD COLUMN {col}"))
                conn.commit()
            except Exception:
                pass  # column already exists


def get_db() -> Generator[Session, None, None]:
    assert _SessionLocal is not None, "Database not initialized. Call init_db() first."
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
