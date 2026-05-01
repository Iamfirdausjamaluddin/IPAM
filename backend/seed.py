"""
Seed the ip_addresses table with the same 6 example IPs that were
previously hardcoded as FAKE_IPS in main.py.

Run: python seed.py

Idempotent: safe to run more than once. If a row already exists for an
IP (matched by the unique 'ip' column), it is updated instead of inserted.
"""
from sqlalchemy import select

from database import SessionLocal
from models import IPAddress

SEED_DATA = [
    {"ip": "10.10.14.1",  "status": "gateway",  "hostname": "pfsense",     "is_alive": True},
    {"ip": "10.10.14.10", "status": "in_use",   "hostname": "ad-dc-01",    "is_alive": True},
    {"ip": "10.10.14.11", "status": "in_use",   "hostname": "pki-root-ca", "is_alive": True},
    {"ip": "10.10.14.20", "status": "reserved", "hostname": "future-vm",   "is_alive": False},
    {"ip": "10.10.14.50", "status": "free",     "hostname": None,          "is_alive": False},
    {"ip": "10.10.14.99", "status": "rogue",    "hostname": "unknown",     "is_alive": True},
]


def seed() -> None:
    """Insert or update every row in SEED_DATA."""
    inserted = 0
    updated = 0

    # Open a session — the unit of work for talking to the DB.
    # Using 'with' guarantees the session is closed even if something blows up.
    with SessionLocal() as session:
        for entry in SEED_DATA:
            # Look for an existing row with the same IP.
            stmt = select(IPAddress).where(IPAddress.ip == entry["ip"])
            existing = session.scalars(stmt).one_or_none()

            if existing is None:
                # Brand new IP — create a row from the dict and add it.
                session.add(IPAddress(**entry))
                inserted += 1
            else:
                # Already exists — overwrite its fields with the seed values.
                # This keeps the seed authoritative if you re-run it after edits.
                existing.status = entry["status"]
                existing.hostname = entry["hostname"]
                existing.is_alive = entry["is_alive"]
                updated += 1

        # Nothing has actually been written to Postgres yet — SQLAlchemy
        # has been queueing changes in memory. commit() sends them as a
        # single transaction. If anything fails, none of it persists.
        session.commit()

    print(f"Seed complete: {inserted} inserted, {updated} updated.")


if __name__ == "__main__":
    seed()