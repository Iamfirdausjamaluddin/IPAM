"""
IPAM Backend API  Phase 1
A minimal FastAPI app that returns hardcoded IP data.
Real database and scanner come in later phases.
"""

from fastapi import FastAPI

# Create the FastAPI application instance.
# The 'title', 'description', and 'version' show up in the auto-generated /docs page.
app = FastAPI(
    title="Homelab IPAM API",
    description="IP Address Management for the homelab subnet 10.10.0.0/20",
    version="0.1.0",
)


# Hardcoded fake data for Phase 1.
# In Phase 2 this will come from PostgreSQL.
# In Phase 3 the 'is_alive' field will be updated by the scanner.
FAKE_IPS = [
    {"ip": "10.10.14.1",  "status": "gateway",  "hostname": "pfsense",     "is_alive": True},
    {"ip": "10.10.14.10", "status": "in_use",   "hostname": "ad-dc-01",    "is_alive": True},
    {"ip": "10.10.14.11", "status": "in_use",   "hostname": "pki-root-ca", "is_alive": True},
    {"ip": "10.10.14.20", "status": "reserved", "hostname": "future-vm",   "is_alive": False},
    {"ip": "10.10.14.50", "status": "free",     "hostname": None,          "is_alive": False},
    {"ip": "10.10.14.99", "status": "rogue",    "hostname": "unknown",     "is_alive": True},
]


@app.get("/")
def read_root():
    """Root endpoint a friendly hello to confirm the API is up."""
    return {
        "name": "Homelab IPAM API",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/health")
def health_check():
    """Health check endpoint  used by Docker and Kubernetes later."""
    return {"status": "ok"}


@app.get("/ips")
def list_ips():
    """Return the list of IPs with their current status."""
    return {"count": len(FAKE_IPS), "ips": FAKE_IPS}