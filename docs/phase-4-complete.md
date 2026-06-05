# Phase 4 Complete — Frontend Dashboard
Branch: `phase-4-frontend`. Final commit: `9d8b53a` —
"Phase 4.6: color grid, subnet tabs, click-to-reserve, per-tab health summaries".
Builds on the mid-phase checkpoints in `docs/phase-4-progress-4.5.md`.

## What Phase 4 delivered
A working React dashboard for the IPAM, talking to the FastAPI backend over
JSON. Single file: `frontend/src/App.jsx` (React + Vite + Tailwind v3, dev
server pinned to port 5174). The dashboard now does the full loop the project
set out to do: see IP status at a glance, and safely claim IPs before building
VMs.

### Feature breakdown (sub-steps 4.6.1 → 4.6.6)
- **4.6.1 — Color grid.** Fetches `GET /grid/{tab}` and renders 256 cells in a
  16x16 layout, colored by the locked legend (green=free, blue=in_use,
  orange=reserved, red=rogue, gray=system). Status -> class via a *static*
  map (Tailwind can't see dynamically-built class names).
- **4.6.2 — Subnet tab strip.** Tabs 11-15; selecting one drove a refetch via
  the effect's dependency array.
- **4.6.4a — Read-only side panel.** Clicking a cell opens a panel showing the
  IP, a colored status pill, and (via `GET /reservations/{ip}`) the existing
  reservation. A 404 from that endpoint is treated as "unclaimed", not an error.
- **4.6.4b — Reservation form (create / edit / release).** The panel became a
  form writing to the backend: POST to create, PUT to edit, DELETE to release.
  Form strings are converted to the schema's types on save (empty -> null,
  vm_id -> number/null). Backend error `detail` (e.g. 409 already-reserved,
  404 not-in-range) is surfaced to the user. System addresses show no form.
- **4.6.6 — Per-tab health summaries.** All five subnet grids are now loaded up
  front with `Promise.all`, so every tab shows its own `N used · M free` count
  and tab switching is instant (no per-tab fetch). A `refreshKey` counter
  forces a full reload after any save/release, so counts and colors stay live.

(Note: the originally-planned 4.6.3 "backend reservation endpoints" was found
to already exist in `main.py` — full CRUD with 409/404 guards — so it was
checked off without new work. Step numbering reflects that.)

## Verified (on the dev machine, live against Postgres)
- Grid renders 256 cells for `10.10.15.x`; matched the known tally (system .0
  and .255 gray, one rogue red, rest green).
- Tabs switch instantly; each shows its own used/free count.
- Reserve a free IP -> cell recolors and the tab count updates on the spot.
- Reservations persist across a full page reload (confirmed DB write, not just
  React state).
- Edit and Release round-trip correctly; releasing returns a cell to free.
- System cells (.0/.255/gateway) correctly offer no reservation form.

## Real-world onboarding done
- `10.10.15.70` (SVR1) and `10.10.15.71` (SVR2) reserved — the first real VMs
  claimed in the IPAM. Both answer ping, so once a scan cycle confirms them
  alive they read blue (in_use); orange in the interim.
- Still to onboard at user's pace: DC `10.10.15.20`, and known hosts
  `10.10.13.10`, `10.10.13.22`, `10.10.14.12`.

## Key things learned / confirmed this phase
- **The "green trap" is real and is the whole reason the tool exists.** A
  powered-off OR ping-blocking VM with no reservation reads green (free) and
  would invite an IP conflict. Reservations (intent) are the only thing that
  protects such an IP, independent of ping (observation). This validated the
  dual-source design end to end.
- **`.70`/`.71` answer ping after all.** The earlier 4.5 assumption that
  SVR1/SVR2 block ICMP was disproved by a live `ping` test (0% loss). They had
  read green because they were *powered off* at scan time (`is_alive=f`), not
  because ICMP was blocked. Lesson: trust the live environment over the notes.
- **Status is never auto-assigned.** The system refuses to auto-reserve a host
  it sees alive, because "alive but unclaimed" (rogue/red) is the alarm that
  distinguishes a legitimate host from a rogue device. Auto-blue would silence
  that alarm. Blue requires the human act of reserving.
- **Tailwind dynamic-class gotcha** documented: status colors must be a static
  literal-string map, never `bg-${x}-500`.

## Scanner depth — researched, decided, deferred (Phase 3.5 candidate)
Compared the project's scanner against NetBox (Django + PostgreSQL + Redis;
intent-only core, with a *separate* Go "orb-agent" / NetBox Discovery doing
NMAP-based scanning and Diode ingestion) and phpIPAM (PHP/MySQL, scans). Core
stack choices (Python + PostgreSQL, API-first) align with the industry standard;
FastAPI + React SPA is a modern alternative to NetBox's Django monolith; the
in-process active scanner is a deliberate homelab-scale choice.

**Decision: adopt "Tier 1" as a future Phase 3.5 (scanner) change — NOT done
yet.** Tier 1 = add a TCP-connect liveness probe alongside `icmplib`, so a host
counts as alive if it answers ping OR accepts a TCP connection on a common port
(3389/445 for Windows, 22 for Linux). Closes the documented ICMP-blind-spot
limitation, stays pure Python / in-process, needs no DB migration and no
frontend change.

Explicitly OUT of scope for Tier 1 (would touch architecture / break rules):
- **rDNS observed-hostname lookup** — dropped; full PTR coverage would require
  configuring pfSense DNS (non-negotiable). `reservations.hostname` (typed
  intent) remains the source of truth.
- **MAC auto-discovery** — impossible in this routed topology (ARP doesn't
  cross pfSense / the Tailscale subnet router; even NMAP can't). `mac_address`
  stays a manual reservation field by design.

Considerations recorded for when Tier 1 is built:
- Probe TCP *only when ping fails* (less noise, targets the blind spot).
- Keep existing rails: 50 concurrent cap, short per-probe timeout (~1s).
- Still pfSense-safe (just sockets) but louder — the section-12 note to
  whitelist the scanner under Snort/Suricata matters more.
- On adoption, UPDATE `homelab-context.md` section 8 (currently locks scanner
  to `icmplib` only) to "icmplib + TCP-connect liveness probe".
- Do it on a dedicated `phase-3.5-scanner` branch, touching only `scanner.py`.

## Outstanding cleanup items (carried; not blocking)
1. `hostname` nullability mismatch — `ip_addresses.hostname` is NOT NULL in DB,
   model declares `nullable=True`. (from 4.4)
2. `is_alive` default mismatch — DB column NOT NULL no default, model declares
   `default=False`. (from 4.4)
3. Vite scaffold leftovers — unused `App.css` / SVGs in `frontend/src/`.
4. Legacy `status` column on `ip_addresses` now redundant (grid computes status
   fresh via `status.py`); decide keep-vs-drop.
5. MAC format regex still deferred to a later polish pass.

## Next
- **Phase 3.5 (recommended next, short):** implement the Tier 1 TCP-connect
  probe in `scanner.py` per the considerations above.
- **Phase 5 (roadmap):** Containerization — Dockerfile + docker-compose for the
  full app. (Note for Phase 5: a TCP-probe scanner is pure Python, so no extra
  system packages needed in the image — unlike full NMAP, which would have.)
