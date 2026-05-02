"""
Populates the ip_addresses table with one row per IP in the assignment range.

This script is idempotent: running it twice does nothing the second time.
The scanner (Phase 3) updates these rows; this script only ensures they exist.

Range: 10.10.11.10 - 10.10.15.254 (the user's VM assignment range from
homelab-context.md, minus the /20 broadcast 10.10.15.255).
"""
import ipaddress
from sqlalchemy import select

from database import SessionLocal
from models import IPAddress


# Inclusive range, defined once here so it's easy to audit and change.
RANGE_START = ipaddress.IPv4Address("10.10.11.10")
RANGE_END = ipaddress.IPv4Address("10.10.15.254")


def iter_range(start: ipaddress.IPv4Address, end: ipaddress.IPv4Address):
    """Yield every IPv4 address from start to end, inclusive."""
    current = int(start)
    last = int(end)
    while current <= last:
        yield ipaddress.IPv4Address(current)
        current += 1


def populate() -> tuple[int, int]:
    """
    Ensure a row exists for every IP in the assignment range.

    Returns (inserted, skipped) — how many rows were added vs already present.
    """
    inserted = 0
    skipped = 0

    with SessionLocal() as session:
        # Load every IP currently in the table into a set for O(1) lookup.
        # For 1,262 rows this is trivially small; we'd switch to per-row
        # checks if the range ever grew to millions.
        existing = {
            row.ip
            for row in session.scalars(select(IPAddress)).all()
        }

        new_rows = []
        for addr in iter_range(RANGE_START, RANGE_END):
            ip_str = str(addr)
            if ip_str in existing:
                skipped += 1
                continue
            new_rows.append(
                IPAddress(
                    ip=ip_str,
                    status="free",
                    hostname=None,
                    is_alive=False,
                )
            )
            inserted += 1

        if new_rows:
            session.add_all(new_rows)
            session.commit()

    return inserted, skipped


if __name__ == "__main__":
    inserted, skipped = populate()
    print(f"Populate complete: {inserted} inserted, {skipped} skipped (already present).")