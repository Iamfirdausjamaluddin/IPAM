# Step 4.5 Complete — Server-side Status Logic + Grid Endpoint
Part of Phase 4 (Frontend). Mid-phase checkpoint. Branch: `phase-4-frontend`.
Commit: `<fill in>` — "Phase 4.5: compute_status, is_system_address, grid endpoint"

## What was built
- **`status.py`** (new) — pure logic, no DB / no FastAPI / no network:
  - `IPStatus` enum (`str, Enum`): `free`, `in_use`, `reserved`, `rogue`,
    `system`. Inherits `str`, so it serializes straight to its string value
    in JSON.
  - `compute_status(*, has_reservation, is_alive, is_system=False)` — the
    2x2 truth table, with `is_system` short-circuiting first (a system
    address is never assignable regardless of the other signals). Keyword-
    only args so two booleans can't be swapped by accident.
  - `is_system_address(ip)` — uses the stdlib `ipaddress` module; returns
    `True` for the gateway `10.10.10.1` and for the `.0`/`.255` of every
    /24 tab (see decision below). Raises `ValueError` on a malformed IP.
- **`grid.py`** (new) — the bridge between DB facts and `status.py` meaning:
  - `compute_subnet_grid(db: Session, third_octet: int) -> list[dict]`.
  - Strategy "all 256, then layer on what we know": generate every address
    in the tab, then TWO bulk queries (one to `ip_addresses` for `is_alive`,
    one to `reservations` for intent), then one Python loop calling
    `compute_status` + `is_system_address`. Two queries total, never one
    per cell (no N+1). Returns `[{"ip": str, "status": IPStatus}, ...]`,
    always exactly 256 entries, ordered `.0`..`.255`.
  - Takes a `Session` argument — deliberately decoupled from `get_db`, so it
    doesn't care how the session is created.
  - `NETWORK_PREFIX = "10.10"` constant.
- **`schemas.py`** — added `IPCell` (`ip: str`, `status: IPStatus`). Minimal
  by design; full side-panel detail is fetched per-IP, not for all 256 cells.
- **`main.py`** — added `GET /grid/{third_octet}` (`response_model=list[IPCell]`):
  - `third_octet` parsed as `int` by FastAPI (non-numeric path -> 422).
  - `TRACKED_SUBNETS = range(11, 16)`; out-of-scope tab -> friendly 404,
    mirroring the Guard-2 pattern in `create_reservation`.
  - Thin wrapper: validate, call `compute_subnet_grid`, return.
  - API `version` bumped `0.3.0` -> `0.4.0` (cosmetic).

## Verified
- `compute_status`: all 8 truth-table combinations asserted.
- `is_system_address`: edges True; gateway True; a `.1` that is NOT the
  gateway (`10.10.11.1`) -> False (we gray the gateway only, not every `.1`);
  known hosts -> False; malformed IP raises `ValueError`.
- `grid.py` against the REAL models on a throwaway SQLite DB: reserved-but-
  never-pinged -> `reserved`; IP in neither table -> `free`; 256 cells.
- Live Postgres tally for `10.10.15.x`: `{free: 253, system: 2, rogue: 1}`.
- Live endpoint via FastAPI TestClient: `/grid/15` -> 200 (256 cells, all
  five states correct); `/grid/99` -> 404; `/grid/abc` -> 422; OpenAPI
  documents `IPStatus` as the five values.
- Swagger on the dev machine: `/grid/15` -> 200, real cells returned. PASS.

## Key decisions
- **Status logic is computed, not stored, and lives in exactly one place
  (`status.py`).** SQL does NOT compute status (no `CASE` expression) — that
  would duplicate the rules and let them drift. The DB stores facts; Python
  decides meaning.
- **System-address policy = Option B (/24 display convention).** `.0` and
  `.255` of each tab are grayed as `system` even though a strict /20 would
  allow them as host IPs. Costs ~9 otherwise-usable addresses (negligible);
  chosen for the familiar subnet-grid look. A visual-only edge hint can be
  added later WITHOUT locking those IPs, if the strict-correctness view is
  ever wanted.
- **Grid endpoint returns minimal `{ip, status}`** — just enough to color a
  square. Side-panel detail (hostname, MAC, note, last_seen, reserved_by) is
  fetched one IP at a time on cell click.
- **ICMP limitation confirmed live, by design.** In the `15.x` tally, the DC
  / SVR1 / SVR2 (which block ping) read as `free`, not `rogue`, because the
  scanner can't see them. This is the documented Phase-3 limitation working
  as accepted. Reservations are intent-based and independent of ping, so once
  reserved those hosts will read `reserved` (orange) regardless of ICMP, and
  `in_use` (blue) if they ever do answer. This validates the dual-source
  (observation vs intent) architecture.

## Outstanding cleanup items (not blocking; address before phase end)
1. **`hostname` nullability mismatch** — `ip_addresses.hostname` is `NOT NULL`
   in the DB, model declares `nullable=True`. (carried from 4.4)
2. **`is_alive` default mismatch** — DB column `NOT NULL` with no default,
   model declares `default=False`. (carried from 4.4)
3. **Vite scaffold leftovers** — unused `App.css` / SVGs in `frontend/src/`.
   (carried from 4.4)
4. **Legacy `status` column on `ip_addresses` is now redundant.** The grid
   computes status fresh via `status.py`; the stored column is no longer the
   source of truth. Decide keep-vs-drop (the scanner may still write it).
   (new)
5. **MAC format regex** still deferred to a later polish pass. (carried from 4.4)

## Next: Step 4.6 — wire `/grid` into the React grid
- Subnet tab strip (11-15), each tab fetching `GET /grid/{tab}`.
- Render a color-coded grid of 256 cells per the locked legend
  (green=free, blue=in_use, orange=reserved, red=rogue, gray=system).
- Side panel on cell click: fetch per-IP detail (e.g. `GET /reservations/{ip}`
  plus the IP's observation fields) rather than carrying detail in the grid
  payload.
- Tab health summaries ("N used / M free") computed client-side from the
  returned cells.
