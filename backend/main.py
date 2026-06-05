"""
IPAM Backend API — Phase 3 + Phase 4 (CORS + grid endpoint)

FastAPI app with a background ICMP scanner. The scanner runs every
5 minutes inside the same process as the API, updating is_alive and
last_seen columns in the ip_addresses table.

Phase 4 adds CORS middleware so the React dev server at localhost:5174
can call this API from the browser, plus the GET /grid/{third_octet}
endpoint that serves the computed per-IP status for one /24 tab.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from dependencies import get_db
from grid import compute_subnet_grid
from models import IPAddress, Reservation
from scanner import scan_all_ips
from schemas import IPCell, ReservationCreate, ReservationRead, ReservationUpdate


# Show INFO-level logs from our own modules so we can see scanner progress.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# How often the background scanner runs a full pass.
# Per homelab-context.md section 12, full scans are spaced 5 minutes apart.
SCAN_INTERVAL_SECONDS = 300

# The /24 tabs the dashboard tracks: the third octet of 10.10.X.x.
# Matches the tabs listed in homelab-context.md section 13 (11 through 15).
TRACKED_SUBNETS = range(11, 16)  # 11, 12, 13, 14, 15


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
    version="0.4.0",
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
        "version": "0.4.0",
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


@app.get("/grid/{third_octet}", response_model=list[IPCell])
def get_subnet_grid(third_octet: int, db: Session = Depends(get_db)):
    """
    Return the computed status for all 256 IPs of one /24 tab.

    {third_octet} is the tab number (11-15). FastAPI parses it as an int,
    so a non-numeric path like /grid/abc is rejected with a 422 before this
    function runs. We then check it's a tab we actually track and return a
    friendly 404 if not — mirroring the out-of-range guard in
    create_reservation.

    The real work happens in grid.compute_subnet_grid(), which joins the
    scanner's observations with the user's reservations and runs each IP
    through status.compute_status(). This endpoint is a thin wrapper:
    validate the input, hand off, return the list.

    response_model=list[IPCell] guarantees the output shape — every element
    is {"ip": "...", "status": "free|in_use|reserved|rogue|system"}.
    """
    if third_octet not in TRACKED_SUBNETS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Subnet 10.10.{third_octet}.x is not tracked. "
                f"Valid tabs are 11-15."
            ),
        )

    return compute_subnet_grid(db, third_octet)


@app.get("/reservations", response_model=list[ReservationRead])
def list_reservations(db: Session = Depends(get_db)):
    """
    Return every reservation, ordered by IP.

    response_model=list[ReservationRead] tells FastAPI to validate and
    serialize each row through the ReservationRead schema — so the JSON
    output shape is guaranteed, and Swagger documents it automatically.
    """
    stmt = select(Reservation).order_by(Reservation.ip)
    return db.scalars(stmt).all()


@app.get("/reservations/{ip}", response_model=ReservationRead)
def get_reservation(ip: str, db: Session = Depends(get_db)):
    """
    Return a single reservation by its IP.

    The {ip} in the path becomes the 'ip' function argument. We look it up
    by primary key with db.get(). If there's no reservation for that IP,
    we return a 404 instead of letting FastAPI return a confusing error.
    """
    reservation = db.get(Reservation, ip)
    if reservation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No reservation found for IP {ip}",
        )
    return reservation


@app.post(
    "/reservations",
    response_model=ReservationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_reservation(payload: ReservationCreate, db: Session = Depends(get_db)):
    """
    Create a new reservation.

    'payload: ReservationCreate' tells FastAPI to read the request body as
    JSON and validate it against the ReservationCreate schema. If the JSON
    is malformed or missing the required 'ip', FastAPI returns a 422 before
    this function even runs.

    status_code=201 is the HTTP convention for "created something new"
    (vs the default 200 "OK"). Small detail, but it's correct REST.
    """
    # Guard 1: don't allow two reservations for the same IP. Since ip is the
    # primary key, the DB would reject it anyway — but catching it here lets
    # us return a friendly 409 Conflict instead of a raw database error.
    existing = db.get(Reservation, payload.ip)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"IP {payload.ip} is already reserved",
        )

    # Guard 2: the IP must exist in ip_addresses (our FK enforces this, but
    # again — a clean 404 beats a cryptic foreign-key violation).
    ip_exists = db.scalar(select(IPAddress).where(IPAddress.ip == payload.ip))
    if ip_exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"IP {payload.ip} is not in the scanned range",
        )

    # Build the SQLAlchemy row from the validated payload.
    # payload.model_dump() turns the Pydantic object into a plain dict;
    # we unpack it with ** into the Reservation constructor.
    reservation = Reservation(**payload.model_dump())
    db.add(reservation)
    db.commit()
    db.refresh(reservation)  # reload so created_at/updated_at are populated
    return reservation


@app.put("/reservations/{ip}", response_model=ReservationRead)
def update_reservation(
    ip: str, payload: ReservationUpdate, db: Session = Depends(get_db)
):
    """
    Update an existing reservation.

    Every field in ReservationUpdate is optional, so the client can send
    just the fields they want to change. We use exclude_unset=True so that
    fields the client DIDN'T send are left untouched, rather than being
    overwritten with None.
    """
    reservation = db.get(Reservation, ip)
    if reservation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No reservation found for IP {ip}",
        )

    # exclude_unset=True is the key here: it gives us only the fields the
    # client actually included in the request body. Without it, omitted
    # fields would come back as None and wipe existing data.
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(reservation, field, value)

    db.commit()
    db.refresh(reservation)
    return reservation


@app.delete("/reservations/{ip}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reservation(ip: str, db: Session = Depends(get_db)):
    """
    Delete a reservation by IP.

    Returns 204 No Content on success — the HTTP convention for "done,
    nothing to send back." If the reservation doesn't exist, 404.
    """
    reservation = db.get(Reservation, ip)
    if reservation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No reservation found for IP {ip}",
        )

    db.delete(reservation)
    db.commit()
    # No return — 204 means an empty body.