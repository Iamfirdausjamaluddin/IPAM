# Phase 2 Complete — Database

## What was built

PostgreSQL is now the source of truth for IP data. The `/ips` endpoint
queries the database on every request via SQLAlchemy. The hardcoded
`FAKE_IPS` from Phase 1 has been removed entirely.

## New components

- **PostgreSQL 16** running locally in Docker container `ipam-postgres`
  with named volume `ipam-postgres-data` for persistence.
- **`backend/database.py`** — SQLAlchemy engine, `SessionLocal` factory,
  and `Base` declarative class. Reads `DATABASE_URL` and `SQL_ECHO`
  from `.env`.
- **`backend/models.py`** — the `IPAddress` ORM model with seven
  columns: `id`, `ip` (unique, indexed), `status`, `hostname` (nullable),
  `is_alive`, `created_at`, `updated_at`.
- **`backend/dependencies.py`** — `get_db()` FastAPI dependency that
  yields a session per request and closes it after.
- **`backend/seed.py`** — idempotent seeder that inserts/updates the
  same 6 example IPs from Phase 1.
- **Alembic** initialized at `backend/alembic/`. First migration
  `045795083826_create_ip_addresses_table.py` creates the table and
  unique index on `ip`. `env.py` reads `DATABASE_URL` from `.env`
  via the existing `database.py` (no duplicated config).

## Configuration files

- **`backend/.env`** (gitignored) — holds `DATABASE_URL` and `SQL_ECHO`.
- **`backend/.env.example`** (committed) — template with placeholder values.

## Dependencies added to requirements.txt

- `sqlalchemy~=2.0`
- `psycopg[binary]~=3.2`
- `alembic~=1.13`
- `python-dotenv~=1.0`

## API contract

Unchanged from Phase 1, except the version field:

- `GET /` → `{"name": "Homelab IPAM API", "version": "0.2.0", "docs": "/docs"}`
- `GET /health` → `{"status": "ok"}`
- `GET /ips` → `{"count": 6, "ips": [...]}` — same JSON shape, same 6 IPs,
  but every byte is now queried from PostgreSQL.

## How to run from a clean clone

```powershell
git clone https://github.com/Iamfirdausjamaluddin/IPAM.git
cd IPAM/backend

# Bring up Postgres
docker run -d --name ipam-postgres `
  -e POSTGRES_USER=ipam -e POSTGRES_PASSWORD=ipam_dev_password `
  -e POSTGRES_DB=ipam -p 5432:5432 `
  -v ipam-postgres-data:/var/lib/postgresql/data postgres:16

# Python venv + dependencies
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Configure
Copy-Item .env.example .env
# (then edit .env to set the real DATABASE_URL password)

# Apply migrations and seed
alembic upgrade head
python seed.py

# Run
uvicorn main:app --reload
```

## Verifications passed

- `alembic current` reports `045795083826 (head)`
- `psql ... \dt` shows two tables: `alembic_version` and `ip_addresses`
- `psql ... \d ip_addresses` matches the model column-for-column
- `seed.py` reports `6 inserted, 0 updated` on first run, `0 inserted, 6 updated` on second
- `GET /ips` returns the same 6 IPs in the same order as Phase 1
- `Select-String FAKE_IPS` matches only docstrings, not code
- Logs are quiet by default (`SQL_ECHO=false`)

## Decisions worth remembering

- **psycopg v3** chosen over the older psycopg2 — modern, async-capable
  later if needed, no Windows compiler dependency.
- **`server_default=func.now()`** for timestamps so Postgres is the
  source of truth for time, not Python.
- **`unique=True, index=True`** on `ip` — Alembic merged these into
  a single unique index, which is the optimal Postgres pattern.
- **`SQL_ECHO` env var** instead of hardcoding `echo=True/False` —
  configurable per environment, sets up the pattern for Vault later.
- **Idempotent seed** via existence-check-then-add-or-update — safe
  to re-run during development.

## Known limitations / deferred to later phases

- No Pydantic response models yet — `/ips` builds dicts manually from
  ORM rows. To be formalized in a later phase.
- Seed data is still the same 6 fake IPs from Phase 1; real data
  arrives in Phase 3 when the scanner starts populating the table
  with live ping results.
- No tests yet. Tests come in Phase 11 alongside CI/CD.
- `.env` password is plaintext on disk. Vault integration in Phase 9.

## Branch

This phase was developed on `phase-2-database`. To merge into main:

```powershell
git checkout main
git merge phase-2-database
git push
```

## Handoff to Phase 3

Phase 3 builds the background ping scanner. It will:

- Use `icmplib` to ping IPs in the assignment range (10.10.11.10–10.10.15.248).
- Open SQLAlchemy sessions to update `is_alive` (and `last_seen` — a new
  column to be added via a Phase 3 migration).
- Run on a schedule (every 5 minutes, max 50 concurrent pings, 2s timeout
  per `homelab-context.md` §12).
- Replace the Phase 2 fake seed entries with real ping data; the seed
  script becomes obsolete or repurposed as test fixtures.

The seam is already in place — `database.py` and `models.py` are reusable
as-is. The scanner is just another piece of code that imports from them.