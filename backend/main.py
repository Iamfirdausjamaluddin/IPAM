"""
IPAM Backend API — Phase 3 + Phase 4 (CORS added)

FastAPI app with a background ICMP scanner. The scanner runs every
5 minutes inside the same process as the API, updating is_alive and
last_seen columns in the ip_addresses table.

Phase 4 adds CORS middleware so the React dev server at localhost:5174
can call this API from the browser.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from dependencies import get_db
from models import IPAddress
from scanner import scan_all_ips


# Show INFO-level logs from our own modules so we can see scanner progress.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# How often the background scanner runs a full pass.
# Per homelab-context.md section 12, full scans are spaced 5 minutes apart.
SCAN_INTERVAL_SECONDS = 300


async def _scanner_loop() -> None:
    """
    Background loop: run a scan, sleep, repeat. Forever, until cancelled.

    Lives inside the FastAPI process as an asyncio task. Cancellation is
    raised inside asyncio.sleep, which propagates up and ends the loop.
    """
    logger.info("scanner loop: starting")
    try:
        while True:
            await scan_all_ips()
            await asyncio.sleep(SCAN_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        # Normal shutdown path — uvicorn cancels the task during shutdown.
        logger.info("scanner loop: cancelled, exiting")
        raise


@asynccontextmanager
async def lifespan(app):
    """
    FastAPI lifespan handler — runs once at startup, once at shutdown.

    Code before `yield`: startup. Launch the scanner as a background task.
    Code after `yield`: shutdown. Cancel the task and wait for clean exit.
    """
    # Startup
    scanner_task = asyncio.create_task(_scanner_loop())
    logger.info("lifespan: scanner task started")

    yield  # FastAPI serves requests during this period

    # Shutdown
    logger.info("lifespan: cancelling scanner task")
    scanner_task.cancel()
    try:
        await scanner_task
    except asyncio.CancelledError:
        pass  # expected during clean shutdown
    logger.info("lifespan: scanner task stopped cleanly")


app = FastAPI(
    title="Homelab IPAM API",
    version="0.3.0",
    lifespan=lifespan,
)


# CORS — allow the React dev server to call this API from the browser.
# Tight by default: only the Vite dev server origin is allowed.
# When we deploy to K3s in Phase 8, the production frontend origin gets added here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    """Root endpoint — a friendly hello to confirm the API is up."""
    return {
        "name": "Homelab IPAM API",
        "version": "0.3.0",
        "docs": "/docs",
    }


@app.get("/health")
def health_check():
    """Health check endpoint — used by Docker and Kubernetes later."""
    return {"status": "ok"}


@app.get("/ips")
def list_ips(db: Session = Depends(get_db)):
    """
    Return every IP in the database, ordered by ID.

    The 'db' parameter looks like a normal function argument, but FastAPI
    populates it via Depends(get_db) — every request gets a fresh
    SQLAlchemy session that is closed after the response is sent.
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
