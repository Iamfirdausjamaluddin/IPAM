# Phase 3 Complete — IP Scanner

## What was built

The IPAM is now actively monitoring the network. An async ICMP scanner
runs every 5 minutes inside the FastAPI process, pinging every IP in the
assignment range and writing results to PostgreSQL. The `/ips` endpoint
now reflects real, current network state — not seed data.

## New components

- **`backend/scanner.py`** — async ICMP scanner using `icmplib`.
  - `ping_ips(ips)` — pure ping function, no DB. Returns
    `list[PingResult]` with `is_alive` per IP.
  - `scan_all_ips()` — orchestrator: load IPs from DB, ping them, write
    results back. Self-contained, opens its own sessions, catches all
    exceptions so a failed cycle does not kill the background task.
- **`backend/db_writer.py`** — `apply_results(session, results)` updates
  `is_alive` for every result and sets `last_seen=NOW()` on alive pings.
  Status is intentionally NOT touched by the scanner; that is Phase 4's
  job.
- **`backend/scan_types.py`** — neutral module holding the `PingResult`
  dataclass. Exists to break a circular import between `scanner.py` and
  `db_writer.py`.
- **`backend/seed.py`** — repurposed from Phase 2's hand-picked seed
  into a range populator. Idempotently ensures one row exists per IP in
  10.10.11.10–10.10.15.254, defaulting `status='free'`. Excludes the /20
  broadcast 10.10.15.255 to avoid pinging it.
- **`backend/main.py`** — FastAPI `lifespan` handler launches
  `_scanner_loop` as an `asyncio.create_task` on startup, cancels it
  cleanly on shutdown. Module-level `logging.basicConfig` shows scanner
  progress in the terminal.

## Schema change

- Added `last_seen` (`timestamp with time zone`, nullable) to
  `ip_addresses`.
- Migration `d0cf9f02ac75_add_last_seen_to_ip_addresses.py` applied via
  `alembic upgrade head`.

## Configuration constants

Defined in `scanner.py`, derived from `homelab-context.md` §12:

- `MAX_CONCURRENT = 50`
- `PING_TIMEOUT_SECONDS = 2`
- `PING_COUNT = 1`
- `SCAN_INTERVAL_SECONDS = 300` (in `main.py`)

## Dependency added

- `icmplib~=3.0` (added to `requirements.txt`)

## API contract

- `GET /` → `{"name": "Homelab IPAM API", "version": "0.3.0", "docs": "/docs"}`
- `GET /health` → unchanged
- `GET /ips` → same JSON shape, but `is_alive` and `last_seen` reflect
  live ping data. Row count ≈ 1,269 (1,262 in range + Phase 2 seed
  leftovers outside the range).

## How the pipeline runs

1. `uvicorn main:app` starts the API.
2. The lifespan handler launches `_scanner_loop` as a background task.
3. The loop:
   - calls `scan_all_ips()`
   - sleeps 300 seconds
   - repeats
4. `scan_all_ips()`:
   - reads IP list from DB (short session)
   - calls `ping_ips()` (50 concurrent pings, 2s timeout each, ~50s total)
   - opens a fresh session and writes results via `apply_results()`
5. The API serves requests during scans (asyncio cooperation).
6. Ctrl+C cancels the scanner task cleanly.

## Verifications passed

- `alembic current` shows the new revision as head.
- `\d ip_addresses` shows 8 columns including `last_seen`.
- `python seed.py` is idempotent (0 inserted on second run).
- Standalone scanner test (now removed) showed real VMs as alive.
- `/ips` JSON shows `is_alive:true` for known-running VMs.
- Multiple `/ips` requests succeed *during* an active scan, proving the
  background task does not block the API.
- Ctrl+C produces a clean shutdown log sequence.

## Decisions worth remembering

- **Three-module architecture** for the scanner: `scanner.py` (ping
  logic), `db_writer.py` (DB writes), `scan_types.py` (shared types).
  Each has one reason to change. Avoids the circular import that nearly
  bit us during development.
- **`privileged=True` is required on Windows** for icmplib raw sockets.
  Dev on Windows requires running uvicorn from an elevated PowerShell.
  In Phase 8 (K3s on Linux), the scanner pod will use `NET_RAW`
  capability or unprivileged ping (`ping_group_range`); we will revisit
  the privileged flag at that point.
- **Scanner does not touch `status`.** It only updates `is_alive` and
  `last_seen`. Status is computed in Phase 4 by combining ping data
  with reservation data, in one place.
- **Pre-populate rows over upsert-on-the-fly.** A row exists for every
  IP in the range before the scanner runs, so the dashboard in Phase 4
  has a row to color (including green for "free, never pinged").
- **Two short DB sessions per scan cycle**, not one long-lived one.
  Reads IPs first session, closes it, does network work, writes results
  in second session. Avoids holding a connection for the duration of
  a scan.
- **`asyncio.CancelledError` is re-raised**, not swallowed. This signals
  cooperative cancellation back to the lifespan handler so shutdown
  proceeds cleanly.
- **Module-level `logging.basicConfig` in main.py** so our INFO logs
  are visible alongside uvicorn's. Will revisit when we add structured
  logging in Phase 10 observability.

## Known limitations and operating expectations

- **The scanner reports IPs that respond to ICMP. Hosts with ICMP
  blocked at the OS firewall (default on most Windows servers) will not
  appear alive even when they are.** This is a deliberate Phase 3
  limitation. The Phase 4 reservation system will be the canonical
  source of truth for IP assignment; ping is one signal among several.
- **On the user's homelab, 6 of 9 running VMs respond to ping**: DC,
  SVR1, SVR2, plus 10.10.13.10, 10.10.13.22, 10.10.14.12. The other
  3 VMs are silent and will be marked 🟡 (reserved, not pinging) once
  Phase 4 reservations exist.
- **Windows dev environment requires elevation.** PowerShell must be run
  as Administrator and execution policy allowed for the venv activation
  script. This requirement does not apply to the eventual production
  deployment on K3s/Linux.
- **`uvicorn --reload` interferes with the scanner.** Each save kills
  the scanner mid-cycle. For Phase 3 verification, run `uvicorn main:app`
  without `--reload`.
- **Phase 2 seed leftovers persist** in the table (rows like 10.10.14.10
  with hostname='ad-dc-01', status='in_use'). They are harmless and
  useful for testing Phase 4's color logic against varied data. Can be
  reset with one SQL UPDATE if desired.
- **No tests yet.** Tests come in Phase 11 with CI/CD.

## Out of scope (deferred)

- Pydantic response models — `/ips` still builds dicts manually. Phase 4.
- Authentication on the API. Phase 8.
- ARP-based scanning (would catch ICMP-blocking hosts). Post-deployment
  enhancement, requires the scanner to live on the same L2 segment as
  targets.
- DHCP lease cross-reference with pfSense API. Future enhancement.
- Per-IP scan history (currently `last_seen` is overwritten). Future.

## Branch

This phase was developed on `phase-3-scanner`. Merged to main:

```powershell
git checkout main
git merge phase-3-scanner
git push
```

## Handoff to Phase 4

Phase 4 builds the React + Vite + Tailwind frontend. It will:

- Consume the existing `GET /ips` endpoint (response shape unchanged
  since Phase 2; only `is_alive` and `last_seen` values are new).
- Build the subnet-tab dashboard from `homelab-context.md` §13:
  five tabs (10.10.11.x through 10.10.15.x), each a 256-cell grid.
- Implement the five-color status logic in one place — likely a
  `compute_status(reservation, ping_result) -> Color` function — that
  combines reservation data with `is_alive` to produce the cell color.
- Add the side panel for cell click: IP, status, hostname, VM ID,
  last_seen, reserved-by, note.
- Introduce the reservations API (POST/PUT/DELETE on a new
  `reservations` table) so the user can mark which IPs are intentionally
  assigned. The scanner will continue to ignore status; the API will
  compute display status server-side or send raw signals to the frontend.

Phase 4's first migration will add a `reservations` table (or extend
`ip_addresses` with reservation fields — design decision in Phase 4).
The scanner does not need any changes for Phase 4.