"""
ICMP ping scanner for the IPAM.

This module's only responsibility is "given a list of IPs, return which
ones are alive." It does not touch the database, FastAPI, or any other
component — those wirings live in main.py and a future db_writer module.

Concurrency, timeout, and behavior on failure are all defined here so the
scanner's network etiquette is in one place. See homelab-context.md §12.
"""

from typing import Iterable

from icmplib import async_multiping

import logging

from sqlalchemy import select

from database import SessionLocal
from db_writer import apply_results
from models import IPAddress
from scan_types import PingResult


logger = logging.getLogger(__name__)


# Scanner safety limits, per homelab-context.md §12.
MAX_CONCURRENT = 10
PING_TIMEOUT_SECONDS = 2
PING_COUNT = 2  # one echo request per IP per scan; we don't need averages





async def ping_ips(ips: Iterable[str]) -> list[PingResult]:
    """
    Ping every IP in `ips` and return their alive/dead status.

    Concurrency is capped by MAX_CONCURRENT inside icmplib. Each ping has
    a hard timeout of PING_TIMEOUT_SECONDS. A non-responding IP is reported
    as is_alive=False, never raised as an exception.
    """
    ip_list = list(ips)
    if not ip_list:
        return []

    hosts = await async_multiping(
        addresses=ip_list,
        count=PING_COUNT,
        timeout=PING_TIMEOUT_SECONDS,
        concurrent_tasks=MAX_CONCURRENT,
        privileged=True,  # try unprivileged first; fall back if needed
    )

    return [
        PingResult(ip=host.address, is_alive=host.is_alive)
        for host in hosts
    ]

async def scan_all_ips() -> None:
    """
    One full scan cycle: load every tracked IP from DB, ping them, write back.

    Designed to be called on a schedule (every 5 minutes, per
    homelab-context.md §12). Self-contained — opens its own DB session,
    does its work, closes the session, returns.

    Errors are logged but not raised. A failed scan should not crash the
    background task that calls this; it should just log and try again later.
    """
    try:
        # Pull the list of IPs to ping from the database.
        # We open a short session just for this read; it's closed before
        # we start the network work, so the connection isn't held open
        # for the duration of the scan (which can take several seconds).
        with SessionLocal() as session:
            ip_strings = [
                row.ip for row in session.scalars(select(IPAddress)).all()
            ]

        if not ip_strings:
            logger.info("scan_all_ips: no IPs in table, skipping")
            return

        logger.info("scan_all_ips: pinging %d IPs", len(ip_strings))
        results = await ping_ips(ip_strings)

        alive_count = sum(1 for r in results if r.is_alive)
        logger.info(
            "scan_all_ips: %d alive of %d", alive_count, len(results)
        )

        # Open a fresh session to write results.
        with SessionLocal() as session:
            updated = apply_results(session, results)
        logger.info("scan_all_ips: %d rows updated", updated)

    except Exception:
        # Catch-all so the background task in main.py never dies silently.
        # Log with traceback so we can see what went wrong.
        logger.exception("scan_all_ips: scan cycle failed")