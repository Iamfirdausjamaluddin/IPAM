"""
grid.py - builds the per-IP status list that the dashboard grid renders.

This is the bridge between the database (raw facts) and status.py (meaning).
It does NOT decide what any status means - that stays in status.py. Its only
job is: gather the facts for one /24 tab, then ask status.py to interpret them.

Strategy ("all 256, then layer on what we know"):
  1. Generate every address in the tab (10.10.<tab>.0 .. .255).
  2. Two bulk queries load whatever we happen to know:
       - which of those IPs the scanner has seen, and whether each is alive
       - which of those IPs have a reservation row
  3. Loop the 256 addresses, look up those two facts (defaulting to
     "not seen / not reserved" when an IP is in neither table), and call
     compute_status() + is_system_address() to get the cell's status.

Two queries total, no matter how big the tab - never one query per cell.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import IPAddress, Reservation
from status import compute_status, is_system_address

# Fixed for this homelab: every tab is 10.10.<third_octet>.x inside 10.10.0.0/20.
NETWORK_PREFIX = "10.10"


def compute_subnet_grid(db: Session, third_octet: int) -> list[dict]:
    """Return [{'ip': str, 'status': IPStatus}, ...] for one /24 tab.

    `third_octet` is the tab number (11..15 in this homelab). The list always
    has exactly 256 entries, ordered .0 through .255, so the frontend can draw
    a complete grid without worrying about gaps in the database.
    """
    all_ips = [f"{NETWORK_PREFIX}.{third_octet}.{n}" for n in range(256)]

    # 1) Observation - what the scanner has actually seen.
    #    Returns (ip, is_alive) pairs only for IPs that exist in the table;
    #    every other address simply won't appear here.
    observed = db.execute(
        select(IPAddress.ip, IPAddress.is_alive).where(IPAddress.ip.in_(all_ips))
    ).all()
    alive_by_ip = {ip: is_alive for ip, is_alive in observed}

    # 2) Intent - which of these IPs the user has reserved.
    reserved_ips = set(
        db.execute(
            select(Reservation.ip).where(Reservation.ip.in_(all_ips))
        ).scalars().all()
    )

    # 3) Combine. status.py is the ONLY place that decides what the facts mean.
    grid = []
    for ip in all_ips:
        status = compute_status(
            has_reservation=ip in reserved_ips,
            is_alive=alive_by_ip.get(ip, False),
            is_system=is_system_address(ip),
        )
        grid.append({"ip": ip, "status": status})
    return grid
