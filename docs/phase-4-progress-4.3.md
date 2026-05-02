# Phase 4 — Partial Progress (Steps 4.1–4.3 Complete)

This is a mid-phase checkpoint, not a phase completion summary. Phase 4
continues from Step 4.4. Paste this as the first message of the next
Phase 4 chat to resume.

## What's done

The React frontend exists, Tailwind works, and the browser successfully
calls FastAPI and renders real data from Postgres. The frontend↔backend
wire is proven end-to-end.

Currently visible at `http://localhost:5174/`:

> **Homelab IPAM**
> Loaded **1269** IPs from backend. *(6 alive)*

## What was built

- **`frontend/`** — Vite + React 18 + Tailwind v3 scaffold at the repo
  root, alongside the existing `backend/` folder.
- **`frontend/vite.config.js`** — Vite pinned to port **5174** with
  `strictPort: true`. Pinning matters because Docker Desktop +
  WSL2 + an unrelated `taskmanager` project on this machine claim 5173
  by default. Pinning gives us a stable, predictable origin for CORS.
- **`frontend/tailwind.config.js`** — `content` array set to scan
  `index.html` and `src/**/*.{js,jsx}`.
- **`frontend/src/index.css`** — replaced Vite default styles with the
  three Tailwind directives (`@tailwind base; components; utilities;`).
- **`frontend/src/App.jsx`** — minimal "smoke test" component that calls
  `GET /ips` on mount and renders the count plus a quick alive count.
  Will be replaced with the dashboard in Step 4.6.
- **`backend/main.py`** — added `CORSMiddleware`, allowing
  `http://localhost:5174` only (tight-by-default, no wildcards even
  in dev). Allows credentials, all methods, all headers. Production
  origin gets added to this list in Phase 8.

## Configuration constants

- Vite dev server port: **5174** (pinned)
- FastAPI port: **8000** (Phase 1 default, unchanged)
- CORS allowlist: `["http://localhost:5174"]`

## How to run from a cold start

Three things in order, four terminals total (or three — backend and
frontend can share a tab if you split panes).

1. **Start Docker Desktop** (Windows tray) and wait for the whale
   icon to go solid.
2. **Start the database container:**
```powershell
   docker start ipam-postgres
```
3. **Start the backend (Terminal 1):**
```powershell
   cd C:\Users\firdaus.jamaluddin\projects\IPAM\backend
   .\.venv\Scripts\Activate.ps1
   uvicorn main:app
```
   Wait for `Application startup complete` and
   `Uvicorn running on http://127.0.0.1:8000`. The first scan after
   startup takes ~50 seconds; the API serves requests during it.
   Run uvicorn **without** `--reload` (Phase 3 rule — reload kills
   the scanner mid-cycle).
4. **Start the frontend (Terminal 2):**
```powershell
   cd C:\Users\firdaus.jamaluddin\projects\IPAM\frontend
   npm run dev
```
   Open `http://localhost:5174/` in the browser.

## Decisions made for the rest of Phase 4

These are locked in unless we deliberately revisit:

- **`compute_status()` lives on the backend, not the frontend.** Status
  is business logic. Server-side keeps the rules in one place; the React
  cell component just maps a status string to a Tailwind color. Future
  CLI/mobile clients get the same logic for free.
- **Reservations go in a separate `reservations` table.** The current
  `ip_addresses` table mixes observation fields (`is_alive`, `last_seen`)
  with reservation-ish fields (`hostname`, `vm_id`, `mac_address`, `note`)
  that have a different lifecycle. Step 4.4 splits them: scanner owns
  observation, user owns intent. The Step 4.4 migration also drops the
  reservation-ish columns from `ip_addresses`.

## Verifications passed

- `Invoke-WebRequest http://localhost:8000/health` → 200 with
  `{"status":"ok"}`.
- `Invoke-WebRequest http://localhost:8000/ips` → 200 with
  `{count: 1269, ips: [...]}`.
- Browser at `http://localhost:5174/` renders "Loaded 1269 IPs from
  backend. (6 alive)" with no console errors.
- Tailwind utility classes (`text-3xl`, `font-bold`, `bg-slate-100`,
  etc.) render correctly, confirming the CSS pipeline.
- Backend logs show `GET /ips HTTP/1.1 200 OK` when React mounts.
- Phase 3 scanner still runs in the background unchanged.

## Known cosmetic noise (ignore)

- Backend logs occasionally print
  `ConnectionResetError: [WinError 10054] An existing connection was
  forcibly closed by the remote host`. This is uvicorn-on-Windows
  being noisy about the browser opening and closing connections during
  Vite hot-reload. Harmless. Goes away in Phase 8 when the backend
  runs on Linux in K3s.
- The default Vite scaffold left an unused `App.css` and assorted SVG
  files in `frontend/src/`. Not imported anywhere. Cleaning these up
  is a small chore for later — does not affect anything.

## Branch and commits

Working on `phase-4-frontend`. Steps 4.1–4.3 committed and pushed.

```powershell
git log --oneline -1
```
should show the most recent commit message:
`Phase 4.1-4.3: React+Vite+Tailwind scaffold, CORS, frontend reads /ips`

## Resume point — Step 4.4

Next step is the **reservations table + CRUD API**. This is the
biggest single step in Phase 4, with real design surface area. The
plan:

1. Design the `reservations` table schema:
   - `ip` (string, primary key, FK to `ip_addresses.ip`)
   - `hostname`, `vm_id`, `mac_address`, `reserved_by`, `note`
   - `created_at`, `updated_at` timestamps
2. Write the Alembic migration. Two parts:
   - Create `reservations` table.
   - Drop `hostname`, `vm_id`, `mac_address`, `note` columns from
     `ip_addresses` (they're moving to `reservations`). Confirm with
     user before running this — it's destructive.
3. Add the SQLAlchemy `Reservation` model.
4. Add CRUD endpoints: `GET /reservations`, `POST /reservations`,
   `GET /reservations/{ip}`, `PUT /reservations/{ip}`, `DELETE
   /reservations/{ip}`.
5. Test each endpoint via the FastAPI Swagger UI at
   `http://localhost:8000/docs` before any frontend work.
6. Frontend changes for Step 4.4 are deliberately deferred — Step 4.5
   will add `compute_status()` server-side, and Step 4.6 builds the
   dashboard that consumes both. Trying to wire React to reservations
   before status logic exists would force rework.

Step 4.4 should be a single chat. Step 4.5 onwards builds on it.