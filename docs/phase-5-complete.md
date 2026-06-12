# Phase 5 Complete — Containerization
Branch: `phase-5-containerization`. The whole app — Postgres, the FastAPI API +
in-process scanner, and the React UI — now comes up from a single
`docker compose up` at the repo root.

## What Phase 5 delivered
Three hand-started processes (a manual `ipam-postgres` container, a uvicorn
process, a Vite dev server) collapsed into one reproducible stack defined by
`docker-compose.yml`. The images built here are the same artifacts Phase 8 will
deploy to K3s — this phase built the deployment unit, not just a dev convenience.

### Sub-steps
- **5.1 — Externalized backend config.** Replaced hand-rolled `os.getenv` +
  `python-dotenv` with a single `pydantic-settings` `Settings` object
  (`backend/config.py`). `database.py` and the CORS middleware now read from it.
  CORS origins stored as a comma-separated string with a `cors_origins_list`
  property (a `list[str]` field would force ugly JSON-in-env). `DATABASE_URL`
  required (fails loud at startup); `SQL_ECHO`, `SCAN_INTERVAL_SECONDS` optional.
  `TRACKED_SUBNETS` stayed a code constant (domain logic, not deployment config).
- **5.2 — Backend Dockerfile.** `python:3.12-slim` (matches dev `3.12.1`).
  Deps layer cached separately from code. Startup INLINED in `CMD`
  (`alembic upgrade head && exec uvicorn ...`) instead of a separate
  entrypoint.sh — a `.sh` edited on Windows can carry CRLF and break its shebang
  in a Linux container. Runs as root so the scanner's `NET_RAW` capability is
  effective. `python-dotenv` removed. `.dockerignore` keeps `.venv`/`.env` out.
- **5.3 — Compose: postgres + backend.** Reused the existing
  `ipam-postgres-data` volume via `external: true` (preserved all reservations).
  Backend reaches DB at host `postgres` (service name), the one value that
  differs from dev `.env`. `pg_isready` healthcheck + `depends_on:
  condition: service_healthy` gates the backend's migration so it can't race a
  cold-starting DB. `cap_add: [NET_RAW]` makes `icmplib privileged=True` work.
- **5.4 — Frontend production image.** `App.jsx` API base changed from absolute
  `http://localhost:8000` to relative `/api`; Vite dev proxy added so dev mirrors
  prod. Multi-stage Dockerfile: `node:22-alpine` builds the static bundle →
  `nginx:alpine` serves it and reverse-proxies `/api/` to `http://backend:8000/`
  (trailing slash strips the prefix). SPA `try_files` fallback.
- **5.5 — Frontend into compose.** Third service on `:8080`, `depends_on:
  backend` so nginx can resolve the `backend` upstream at startup.
- **5.6 — Cleanup + docs.** Removed Vite scaffold leftovers (`src/App.css`,
  `src/assets/`); this completion doc; merge to main.

## Verified (live, on the dev machine)
- `docker compose up` brings up all three services; `compose ps` shows
  `postgres (healthy)`, `backend` and `frontend` running.
- **Tailscale-from-container PROVEN** — the highest-risk item. From inside the
  backend container, `icmplib.ping('10.10.15.20', privileged=True)` returned
  alive, 0% loss; a TCP connect to 3389 also succeeded. The WSL2 → Tailscale
  subnet-route propagation works; `NET_RAW` is effective (no permission error).
- Full stack end to end at `http://localhost:8080`: grid populated, `.20/.70/.71`
  read BLUE (reserved + alive) — the in-container scanner reached the lab through
  Tailscale, wrote `is_alive`, and status computed correctly.
- Browser talks ONLY to `:8080`; nginx proxies `/api` to the backend. No CORS in
  play (single origin) — the same routing pattern Phase 8's Ingress will use.
- Reservations survived the move into compose (reused data volume).

## Key things learned / confirmed this phase
- **Same code, two environments.** The 5.1 config externalization is what lets
  the identical backend image run with `DATABASE_URL` = localhost (dev) or
  `postgres` (compose) with zero code change. This is the whole point of
  config-from-the-outside, and the foundation for K8s ConfigMaps later.
- **Windows lockfile omits Linux optional deps.** `npm ci` failed in the Alpine
  build demanding `@emnapi/*` "missing from lock file," even though
  `npm install` on Windows reported the lockfile in sync. Cause: `@emnapi/*` are
  Linux-only OPTIONAL native deps; a lockfile generated on Windows doesn't record
  them, and strict `npm ci` refuses. Fix for now: `npm install --no-audit
  --no-fund` in the Dockerfile (resolves per-platform inside the image). Trade-off:
  loses npm ci's byte-for-byte reproducibility — fine for homelab. PROPER fix
  deferred to Phase 11 CI: generate the lockfile on Linux (WSL2 / in-container)
  and commit that, or pin the offending dep, so `npm ci` can be restored.
- **nginx resolves upstreams at startup.** `proxy_pass http://backend:8000/`
  makes nginx fail fast with "host not found in upstream" if `backend` doesn't
  exist — which is why the frontend image can't run standalone, and why compose
  needs `depends_on: backend`. Not a bug; the image's job includes the proxy.
- **CRLF risk avoided** by inlining the backend startup in `CMD` (no entrypoint.sh).
- **Healthcheck gating** is what prevents the backend's `alembic upgrade head`
  from racing a not-yet-ready Postgres on cold start.

## Operating the stack (quick reference)
- Start (rebuild if needed): `docker compose up --build` (add `-d` to detach)
- Stop: `docker compose down` (data persists in the volume; `-v` would wipe it)
- After backend code change: `docker compose up --build` (no --reload by design)
- Logs: `docker compose logs backend --tail 50`
- App: http://localhost:8080  ·  API direct: http://localhost:8000  ·  DB: :5432
- Dev loop still available: local uvicorn + Vite, using backend/.env (localhost)

## Carried-forward cleanup items (still not blocking)
1. `hostname` nullability mismatch (DB NOT NULL vs model nullable=True).
2. `is_alive` default mismatch (DB NOT NULL no default vs model default=False).
3. Legacy `status` column on `ip_addresses` redundant (grid computes via
   status.py); decide keep-vs-drop.
4. MAC format regex still deferred.
5. docker-compose.yml comment mojibake (em-dashes) if not yet fixed to UTF-8.

## Next: Phase 6 — Infrastructure as Code
Terraform with the `bpg/proxmox` provider creates the K3s + Vault VMs on Proxmox
(VM ID range 700–799). Terraform commands run in the VS Code PowerShell terminal.
Reminder: never touch pfSense (firewall/DHCP/DNS/NAT/routing) — non-negotiable.
