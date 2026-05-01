"""
FastAPI dependency providers.

These are functions FastAPI calls per-request to inject things like
database sessions into endpoints.
"""
from typing import Generator

from sqlalchemy.orm import Session

from database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    Provide a SQLAlchemy session for one request.

    FastAPI calls this for every request that depends on it. The yielded
    session is the one your endpoint receives. After the response is sent
    (or an exception fires), the code after 'yield' runs and closes the
    session — guaranteeing no leaked connections.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()