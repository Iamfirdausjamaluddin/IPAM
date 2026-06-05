"""
status.py - IP status business logic for the IPAM dashboard.

This module is PURE logic: no database, no FastAPI, no network.
That means every rule here can be checked with a one-line `python -c`,
which is exactly how we verify each step.

An IP's status is computed from at most three signals:
  1. is_system       - is this a network / broadcast / gateway address?
  2. has_reservation - did the user reserve this IP?   (intent)
  3. is_alive        - did the scanner's ping get a reply?  (observation)
"""

import ipaddress
from enum import Enum


class IPStatus(str, Enum):
    """The five possible states for an IP cell in the dashboard grid.

    Inheriting from `str` means FastAPI / Pydantic serialize these straight
    to their string value ("free", "in_use", ...) in JSON automatically,
    while our Python code still gets autocomplete and typo protection
    (IPStatus.RESERVD would be an error; the string "reservd" would not).
    """

    FREE = "free"          # green  - not reserved, not alive -> safe to assign
    IN_USE = "in_use"      # blue   - reserved AND alive -> healthy, as intended
    RESERVED = "reserved"  # orange - reserved but not alive yet -> planned
    ROGUE = "rogue"        # red    - alive but NOT reserved -> alert
    SYSTEM = "system"      # gray   - network/broadcast/gateway -> never assignable


def compute_status(
    *,
    has_reservation: bool,
    is_alive: bool,
    is_system: bool = False,
) -> IPStatus:
    """Return the dashboard status for a single IP.

    The bare `*` makes every argument keyword-only, so a call always reads
    like `compute_status(has_reservation=..., is_alive=...)`. You can never
    silently swap two booleans by accident.

    Rule order matters: `is_system` is checked FIRST, because a system
    address is never assignable regardless of the other two signals.
    """
    if is_system:
        return IPStatus.SYSTEM

    if has_reservation and is_alive:
        return IPStatus.IN_USE
    if has_reservation and not is_alive:
        return IPStatus.RESERVED
    if is_alive and not has_reservation:
        return IPStatus.ROGUE
    return IPStatus.FREE


# The one true system address that the .0/.255 edge rule below would miss
# (its last octet is .1, not .0 or .255), so it needs its own check.
GATEWAY = ipaddress.ip_address("10.10.10.1")


def is_system_address(ip: str) -> bool:
    """Return True if `ip` should be shown as a gray, never-assignable cell.

    Policy (your choice in Step 4.5.2): the display follows the /24 tab
    convention, so the .0 and .255 of every tab are treated as system even
    though a strict /20 would allow them. Parsing through `ipaddress` first
    also means a malformed string raises a clear ValueError instead of
    silently slipping through.
    """
    addr = ipaddress.ip_address(ip)

    # The gateway is a genuine system address with a .1 ending, so the edge
    # rule below won't catch it -- check it explicitly.
    if addr == GATEWAY:
        return True

    # Display convention: the .0 and .255 of every /24 tab are system.
    # This also naturally covers the /20's real network address (10.10.0.0)
    # and broadcast (10.10.15.255), since both already end in .0 / .255.
    last_octet = int(str(addr).split(".")[-1])
    if last_octet in (0, 255):
        return True

    return False