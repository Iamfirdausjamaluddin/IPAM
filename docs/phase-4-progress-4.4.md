# Step 4.4 Complete — Reservations Table + CRUD API

Part of Phase 4 (Frontend). Mid-phase checkpoint. Branch: `phase-4-frontend`.
Commit: `9715b36` — "Phase 4.4: reservations table, Reservation model, CRUD API + schemas"

## What was built

- **`reservations` table** in Postgres (migration `9bcf39c8d5ed`, applied).
  8 columns: `ip` (PK), `hostname`, `vm_id`, `mac_address`, `reserved_by`,
  `note`, `created_at`, `updated_at`. FK `ip -> ip_addresses.ip` with
  `ON DELETE CASCADE`. Timestamps server-defaulted to `now()`,
  `updated_at` auto-bumps on update.
- **`Reservation` SQLAlchemy model** in `models.py` (SQLAlchemy 2.0
  `Mapped`/`mapped_column` syntax).
- **Pydantic v2 schemas** in new file `schemas.py`:
  `ReservationBase`, `ReservationCreate` (requires `ip`),
  `ReservationUpdate` (all optional), `ReservationRead`
  (`from_attributes=True`, includes timestamps).
- **Five CRUD endpoints** in `main.py`:
  - `POST /reservations` (201; Guard 1 = 409 if already reserved,
    Guard 2 = 404 if IP not in scanned range)
  - `GET /reservations` (list, returns array)
  - `GET /reservations/{ip}` (404 if not found)
  - `PUT /reservations/{ip}` (uses `exclude_unset=True` for partial updates)
  - `DELETE /reservations/{ip}` (204 No Content)

## Verified (8 tests via Swagger)

Create (201) -> get one (200) -> list (200) -> partial update (200,
`exclude_unset` protected untouched fields, `updated_at` bumped) ->
delete (204) -> confirm gone (404) -> out-of-range IP (404, Guard 2) ->
duplicate IP (409, Guard 1). All passed.

## Key decisions

- `ip` as primary key (not surrogate int) — clean URLs, IP is naturally unique.
- Status NOT stored on reservation — computed via join in Step 4.5.
- MAC stored as plain string with length cap; format regex validation
  deliberately deferred to a later polish pass.
- Reservations in a separate table from `ip_addresses` — scanner owns
  observation, user owns intent.

## Decided against the original handoff plan

- The previous handoff said "drop `hostname` from `ip_addresses`." We did
  NOT. Decided to keep `hostname` on both tables: on `ip_addresses` it's
  the *observed* hostname (scanner), on `reservations` it's the *intended*
  hostname (user). They can disagree — that disagreement is useful signal
  for a future mismatch-detection feature. Migration `9bcf39c8d5ed` is
  therefore non-destructive (adds the table, drops nothing).
- Note: `vm_id`, `mac_address`, and `note` were never actually present on
  `ip_addresses` (the old handoff assumed they were). Only `hostname`
  existed there, and we kept it.

## Outstanding cleanup items (not blocking, address before phase end)

1. **`hostname` nullability mismatch:** `ip_addresses.hostname` is `NOT NULL`
   in the DB, but the SQLAlchemy model declares `nullable=True`. Reconcile
   these before Phase 4 closes.
2. **`is_alive` default mismatch:** DB column is `NOT NULL` with no default;
   model declares `default=False`. Minor, but note it.
3. **Vite scaffold leftovers:** unused `App.css` and SVG files in
   `frontend/src/` — cosmetic cleanup.

## Environment note (cost a lot of time this session)

An old, unused `taskmanager` Docker project was auto-restarting and
grabbing ports **8000** and **5173** — the same ports IPAM uses. This
caused "wrong app at /docs", "Failed to fetch", and scanner hangs.
**Resolved permanently:** `taskmanager-backend-1` and
`taskmanager-frontend-1` containers and their images were removed
(`docker rm -f` + `docker rmi`). They will not return.

## Next: Step 4.5 — `compute_status()` server-side

Join `ip_addresses` (observation: is_alive) with `reservations` (intent)
to produce the per-IP status: free / in_use / reserved / rogue / system.
This is the business logic the dashboard grid will color-code in Step 4.6.
