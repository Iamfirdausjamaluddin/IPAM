"""
IPAM Backend API — Phase 2

FastAPI app that reads IPs from the PostgreSQL database.
The hardcoded FAKE_IPS from Phase 1 has been removed; data now comes
from the ip_addresses table seeded via seed.py.
"""
from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from dependencies import get_db
from models import IPAddress

app = FastAPI(
    title="Homelab IPAM API",
    description="IP Address Management for the homelab subnet 10.10.0.0/20",
    version="0.2.0",
)


@app.get("/")
def read_root():
    """Root endpoint — a friendly hello to confirm the API is up."""
    return {
        "name": "Homelab IPAM API",
        "version": "0.2.0",
        "docs": "/docs",
    }


@app.get("/health")
def health_check():
    """Health check endpoint — used by Docker and Kubernetes later."""
    return {"status": "ok"}


@app.get("/ips")
def list_ips(db: Session = Depends(get_db)):
    """
    Return every IP in the database, ordered by IP.

    The 'db' parameter looks like a normal function argument, but
    FastAPI populates it via Depends(get_db) — every request gets a
    fresh SQLAlchemy session that is closed after the response is sent.
    """
    stmt = select(IPAddress).order_by(IPAddress.id)
    rows = db.scalars(stmt).all()

    return {
        "count": len(rows),
        "ips": [
            {
                "ip": row.ip,
                "status": row.status,
                "hostname": row.hostname,
                "is_alive": row.is_alive,
            }
            for row in rows
        ],
    }