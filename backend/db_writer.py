"""
Writes scanner results to the ip_addresses table.

This module is the bridge between scanner.py (pure ping logic) and the
database. It is the only place in Phase 3 that touches both PingResult
objects and the ORM session.
"""
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import IPAddress
from scan_types import PingResult


def apply_results(session: Session, results: Iterable[PingResult]) -> int:
    """
    Apply a batch of ping results to the database.

    For each result:
      - is_alive is set to the new value
      - last_seen is set to NOW() only if the ping succeeded
      - updated_at is touched automatically by SQLAlchemy's onupdate hook

    Status is intentionally NOT modified here. Status is a Phase 4 concern
    that combines ping data with reservation data; the scanner only reports
    facts, not interpretations.

    Returns the number of rows updated.
    """
    from sqlalchemy import func  # local import keeps the module surface small

    results_list = list(results)
    if not results_list:
        return 0

    # Build {ip_string: result} for O(1) lookup as we iterate the rows.
    by_ip = {r.ip: r for r in results_list}

    # Load the affected rows in one query instead of one query per IP.
    rows = session.scalars(
        select(IPAddress).where(IPAddress.ip.in_(by_ip.keys()))
    ).all()

    updated = 0
    for row in rows:
        result = by_ip.get(row.ip)
        if result is None:
            continue  # paranoid: shouldn't happen given the WHERE clause

        row.is_alive = result.is_alive
        if result.is_alive:
            row.last_seen = func.now()
        # If not alive, leave last_seen unchanged — the column remembers
        # the most recent time we DID see this IP, which is its job.

        updated += 1

    session.commit()
    return updated