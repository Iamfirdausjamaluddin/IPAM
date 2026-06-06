# Phase 3.5 Complete — Scanner TCP-Connect Liveness Fallback
Branch: `phase-3.5-scanner`. Final commit: `43aa6e8` —
"Phase 3.5: TCP-connect liveness fallback via rolling sweep; ICMP concurrency 10->50".
Off-roadmap sub-phase: a follow-up to Phase 3 (scanner), prompted by a blind
spot that Phase 4 surfaced. Touches only `backend/scanner.py`.

## Why this phase existed
Phase 4 made the ICMP blind spot visible: Windows hosts that block ICMP echo
(Windows Firewall default) read as dead to a ping-only scanner, so a live,
reserved VM showed orange (or a live unreserved one showed green) instead of
its true state. ICMP alone cannot see ping-blocking hosts. Tier 1 adds a second
liveness signal — a TCP-connect probe — so "up but silent to ping" is detected.

## What was built
`probe_ips()` in `scanner.py` now does two stages; `ping_ips()` and the DB
writer are unchanged, and liveness is still a single `is_alive` boolean.

- **Stage 1 — ICMP on every IP, every cycle** (unchanged primary signal).
- **Stage 2 — rolling TCP-connect sweep** over the ping-silent IPs:
  - Ports probed: 445 (SMB), 3389 (RDP), 22 (SSH) — concurrently per host.
  - A host is alive if it answers ping OR accepts a connection on any port.
  - `asyncio.open_connection` + `wait_for`; connect success = port open. No
    data sent. Refused/unreachable -> fast OSError; filtered -> timeout. Needs
    no special privilege (unlike ICMP's raw socket).

### Key design: rolling sweep + sticky set (the hard part)
- **Rolling sweep:** each cycle TCP-probes only a slice of `TCP_SWEEP_SIZE`
  (100) IPs, advancing a module-level cursor that wraps. Full ~1269-IP range is
  covered over ~13 cycles (~1 hr at the 5-min cadence). Ping still hits every
  IP every cycle, so ping-visible changes remain instant.
- **Sticky set (`_tcp_known_alive`):** TCP-confirmed hosts are remembered
  between their sweep turns, so a TCP-only host stays its correct color instead
  of flickering alive/dead as the window moves on/off it. Re-confirmed (and
  dropped if gone) only when its slice comes around again.
- Both bits of state are module-level and reset on process restart — see
  limitations.

### Tuned constants (in `scanner.py`)
- `MAX_CONCURRENT = 50` (ICMP) — raised from 10 to the §12-documented max to
  cut a full ping pass from ~6+ min down to ~2 min for 1269 IPs.
- `TCP_PROBE_PORTS = (445, 3389, 22)`
- `TCP_PROBE_TIMEOUT_SECONDS = 2.0` (per port, tried concurrently)
- `MAX_CONCURRENT_TCP = 20` (IPs per slice probed at once)
- `TCP_SWEEP_SIZE = 100` (silent IPs per cycle)

## The debugging story (why it ended up as a rolling sweep)
First attempt probed ALL silent IPs each cycle. Symptom: a known-open host
(`10.10.13.20`, Windows, RDP/3389 open, blocks ping) was never detected, even
though `Test-NetConnection 10.10.13.20 -Port 3389` succeeded from the laptop.
Ruled out, in order, with standalone diagnostics:
1. **Timeout** — isolated connect to 13.20:3389 returns in <20 ms; 1s was fine.
2. **Concurrency / tunnel saturation** — caught at 5/10/20/40 concurrent.
3. **Probe logic** — correct; caught real hosts.
4. **Windows event loop** — caught under BOTH Proactor and Selector loops.
5. **uvicorn context / HTTP load** — a quiet (no-dashboard) full scan still
   failed, ruling this out.
6. **SCALE (the cause)** — replaying the full ~1269-IP range standalone LOST
   13.20 and found only 6 of the multi-port hosts. Sustained 2-min barrage of
   connection attempts to ~1260 dead IPs floods the routed/Tailscale path with
   packet loss; a single-port host (13.20, RDP only) loses its one reply.
Fix = stop barraging: probe a small slice per cycle (rolling sweep). The slice
size (100) is within the range proven to reliably catch 13.20 in diagnostics.

**Decision: rolling sweep over reserved-scope.** Reserved-scope (probe only
reserved IPs) would have been simpler and smaller, but it cannot discover a
live, ping-blocking host that was never reserved — a "stealth" host. Since the
IPAM's whole purpose is being the authoritative source of truth, catching
unrecorded hosts was judged worth the extra code and the ~1 hr coverage lag.

## Verified
- Standalone diagnostics: TCP mechanics correct; 13.20 caught at small scale,
  LOST at full ~1269 scale (pinpointing the barrage as the cause).
- Sweep + sticky orchestration unit-tested in isolation: cursor wraps; ping-
  alive always alive; truly-dead always dead; TCP-only host detected on its
  slice and then held steady (no flicker); dropped after going offline + its
  next slice.
- Live end to end: reserved `10.10.13.20`; within ~1 hr the sweep reached its
  slice, TCP confirmed 3389, sticky set held it, and the cell turned BLUE
  (reserved + alive) and stayed blue. The exact "silent IP conflict" the
  project exists to prevent, now correctly surfaced.

## Limitations / accepted trade-offs
- **Coverage lag:** a newly-appeared ping-blocking host takes up to ~1 hr (one
  full sweep) to be detected; an offline one takes up to ~1 hr to drop. By
  design.
- **Restart cold-start:** `_sweep_cursor` and `_tcp_known_alive` are in-memory
  and reset on restart; full TCP coverage re-establishes over one sweep pass
  (~1 hr). Ping-visible hosts are unaffected. Could be persisted to DB later if
  wanted.
- **Louder than ping:** TCP probing is more scan-like; the §12 note to
  whitelist the scanner under Snort/Suricata matters more now. Still a passive
  observer — never touches pfSense.
- **MAC / observed-hostname still not auto-discovered** (routed topology; ARP
  doesn't cross pfSense). `mac_address` stays a manual reservation field;
  observed-hostname rDNS deliberately out of scope (would need pfSense DNS).

## Docs updated
- `homelab-context.md` §8: IP scanner row -> "`icmplib` (ICMP) + rolling
  TCP-connect sweep fallback (Phase 3.5)".
- `homelab-context.md` §12: added the TCP-sweep rules (ports, slice size,
  concurrency, timeout, ~1 hr coverage, and the louder-than-ping note).
- (§12 already documented the 50-concurrent ping max; code was simply brought
  in line with it.)

## Carried-forward cleanup items (from Phase 4, still not blocking)
1. `hostname` nullability mismatch (DB NOT NULL vs model nullable=True).
2. `is_alive` default mismatch (DB NOT NULL no default vs model default=False).
3. Vite scaffold leftovers in `frontend/src/`.
4. Legacy `status` column on `ip_addresses` now redundant (grid computes status
   via `status.py`); decide keep-vs-drop.
5. MAC format regex still deferred.

## Next: Phase 5 — Containerization
Dockerfile + docker-compose so the app runs in containers.
- **Watch out:** the scanner's ICMP uses `privileged=True` (raw socket). On
  Windows that meant running as Administrator; in a container it means granting
  a capability (likely `NET_RAW`) or running privileged, or the ICMP half
  fails. The TCP-sweep fallback needs no privilege and partially hedges this.
- The TCP sweep is pure Python (stdlib `asyncio`), so it adds NO system
  packages to the image — unlike full nmap, which would have.
