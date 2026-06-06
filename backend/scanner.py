"""
ICMP ping scanner for the IPAM.

This module's only responsibility is "given a list of IPs, return which
ones are alive." It does not touch the database, FastAPI, or any other
component — those wirings live in main.py and a future db_writer module.

Concurrency, timeout, and behavior on failure are all defined here so the
scanner's network etiquette is in one place. See homelab-context.md §12.

Phase 3.5 adds a TCP-connect fallback (Tier 1) so a host that is up but drops
ICMP (e.g. Windows Firewall's default) is still seen. It uses a ROLLING SWEEP:
TCP-probing all ~1269 IPs every cycle floods the routed/Tailscale path and
drops live hosts' replies (a fragile single-port host like a Windows box with
only RDP open gets lost in the noise). Instead, each cycle probes a small slice
of the silent IPs and rotates through the whole range over many cycles. A
sticky in-memory set remembers TCP-confirmed hosts between their sweep turns so
their status doesn't flicker. Liveness is still a single is_alive boolean;
ICMP stays the primary signal and is checked on every IP every cycle.
"""

import asyncio
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
MAX_CONCURRENT = 50
PING_TIMEOUT_SECONDS = 2
PING_COUNT = 2  # one echo request per IP per scan; we don't need averages


# --- Tier 1: TCP-connect liveness fallback, ROLLING SWEEP (Phase 3.5) --------
# Why a sweep and not "probe every silent IP each cycle": testing showed that
# TCP-probing all ~1260 silent IPs at once sustains a 2-minute barrage of
# connection attempts to non-existent hosts. That floods the routed + Tailscale
# path with packet loss, and a live host with only ONE open port (e.g.
# 10.10.13.20, RDP only) gets its single reply dropped and is missed. A small
# per-cycle slice (proven safe at this size) avoids the flood.
TCP_PROBE_PORTS = (445, 3389, 22)   # SMB, RDP (Windows); SSH (Linux)
TCP_PROBE_TIMEOUT_SECONDS = 2.0     # per port; ports are tried concurrently
MAX_CONCURRENT_TCP = 20             # IPs probed at once within a sweep slice
TCP_SWEEP_SIZE = 100                # silent IPs to probe per cycle; full range
                                    # is covered over ceil(total / this) cycles
                                    # (~13 cycles ≈ 1 hr at the 5-min spacing).

# Sweep state, persisted across scan cycles for the life of the process:
#   _sweep_cursor   - index into the IP list where the next slice starts.
#   _tcp_known_alive - IPs confirmed alive by TCP; "sticky" so a host stays
#                      alive between its sweep turns instead of flickering.
# Both reset on restart: after a restart, full TCP coverage takes one sweep
# pass (~1 hr) to re-establish. Ping-visible hosts are unaffected and update
# every cycle as before.
_sweep_cursor = 0
_tcp_known_alive: set[str] = set()


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


async def _tcp_port_open(ip: str, port: int) -> bool:
    """
    True if a TCP connection to ip:port completes within the timeout.

    open_connection returns once the TCP handshake succeeds — i.e. the port
    is open and accepting connections. We don't send or read any data; we
    only care THAT it connected, then close immediately. A refused/unreachable
    port raises OSError fast; a filtered port never replies, so wait_for cuts
    it off at the timeout. Either way we return False rather than raise.
    """
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port),
            timeout=TCP_PROBE_TIMEOUT_SECONDS,
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except (asyncio.TimeoutError, OSError):
        return False


async def _probe_tcp_alive(ip: str) -> bool:
    """True if ANY port in TCP_PROBE_PORTS accepts a connection (ports tried
    concurrently, so this takes at most ~TCP_PROBE_TIMEOUT_SECONDS)."""
    results = await asyncio.gather(
        *(_tcp_port_open(ip, port) for port in TCP_PROBE_PORTS)
    )
    return any(results)


async def tcp_probe_ips(ips: Iterable[str]) -> set[str]:
    """
    TCP-probe a batch of IPs, at most MAX_CONCURRENT_TCP at a time.
    Returns the set of IPs where at least one probed port accepted a connection.
    """
    ip_list = list(ips)
    if not ip_list:
        return set()

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TCP)

    async def _guarded(ip: str) -> tuple[str, bool]:
        async with semaphore:
            return ip, await _probe_tcp_alive(ip)

    pairs = await asyncio.gather(*(_guarded(ip) for ip in ip_list))
    return {ip for ip, alive in pairs if alive}


async def probe_ips(ips: Iterable[str]) -> list[PingResult]:
    """
    Two-stage liveness: ICMP ping on every IP, plus a rolling TCP sweep.

    Every cycle: ping all IPs. Then take the next TCP_SWEEP_SIZE addresses from
    the full list (wrapping with a cursor that survives across cycles) and
    TCP-probe the ones that were silent to ping. Update the sticky
    _tcp_known_alive set for just those probed IPs. Finally, an IP is alive if
    ping says so OR it is in the sticky set — so TCP-only hosts stay steady
    between their sweep turns instead of flickering.

    Return type is unchanged (list[PingResult]), so callers and the DB writer
    need no changes; we still write all IPs every cycle.
    """
    global _sweep_cursor

    ip_list = list(ips)
    if not ip_list:
        return []

    # Stage 1: ICMP on everything, as before.
    ping_results = await ping_ips(ip_list)
    dead_set = {r.ip for r in ping_results if not r.is_alive}

    # Stage 2: rolling TCP sweep over a small slice of the FULL list.
    n = len(ip_list)
    window_len = min(TCP_SWEEP_SIZE, n)
    window = [ip_list[(_sweep_cursor + i) % n] for i in range(window_len)]
    _sweep_cursor = (_sweep_cursor + window_len) % n

    # Only the silent IPs in this slice are worth probing.
    to_probe = [ip for ip in window if ip in dead_set]
    if to_probe:
        logger.info(
            "probe_ips: TCP sweep — probing %d silent IP(s) in this slice "
            "(%d silent total, cursor now %d/%d)",
            len(to_probe), len(dead_set), _sweep_cursor, n,
        )
        found = await tcp_probe_ips(to_probe)
        # Re-confirm ONLY the IPs we actually probed this cycle: add the ones
        # that answered, drop ones that were known-alive but went quiet.
        for ip in to_probe:
            if ip in found:
                _tcp_known_alive.add(ip)
            else:
                _tcp_known_alive.discard(ip)
        if found:
            logger.info(
                "probe_ips: TCP confirmed alive: %s", ", ".join(sorted(found))
            )

    # Merge: alive if ping saw it OR it's a sticky TCP-known-alive host.
    return [
        PingResult(ip=r.ip, is_alive=r.is_alive or (r.ip in _tcp_known_alive))
        for r in ping_results
    ]


async def scan_all_ips() -> None:
    """
    One full scan cycle: load every tracked IP from DB, probe them, write back.

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

        logger.info("scan_all_ips: probing %d IPs", len(ip_strings))
        # Tier 1: probe_ips = ICMP on all + a rolling TCP sweep for the silent.
        results = await probe_ips(ip_strings)

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