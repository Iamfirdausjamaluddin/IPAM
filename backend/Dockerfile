# Phase 5.2 — Backend image: the IPAM API + its in-process ICMP/TCP scanner.
# Base matches the dev venv exactly (python -V => 3.12.1).
FROM python:3.12-slim

# PYTHONDONTWRITEBYTECODE: don't litter .pyc files in the image.
# PYTHONUNBUFFERED: don't buffer stdout/stderr, so scanner + uvicorn logs show
# up in `docker logs` immediately instead of being held back.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies as their own layer FIRST. Docker caches layers: as long
# as requirements.txt is unchanged, rebuilds reuse this layer and skip the
# (slow) reinstall even when your application code changes. psycopg[binary]
# ships a precompiled wheel, so we need no C compiler / libpq-dev in the image.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the application code (alembic/, alembic.ini, *.py, ...).
# .dockerignore keeps .venv, __pycache__, and .env OUT of this copy.
COPY . .

# Documents the port the API listens on. Publishing it to the host is compose's
# job (5.3); EXPOSE alone doesn't open anything.
EXPOSE 8000

# We deliberately run as ROOT (no USER directive). The scanner's ICMP uses
# icmplib privileged=True (a raw socket) — the same reason uvicorn ran as
# Administrator on Windows. The NET_RAW capability that compose grants in 5.3 is
# only effective for root by default; a non-root user would need an ambient-caps
# setup. Non-root hardening is a deliberate later-phase concern.

# Startup, inlined on purpose (NOT a separate entrypoint.sh): a .sh file edited
# on Windows can be saved with CRLF line endings, which breaks its shebang inside
# a Linux container ("no such file or directory"). Inlining sidesteps that trap.
# Order: bring the DB schema current, THEN start the API. `exec` makes uvicorn
# PID 1 so Docker's stop signal reaches it and the scanner shuts down cleanly.
# No --reload (it kills the background scanner mid-cycle).
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn main:app --host 0.0.0.0 --port 8000"]
