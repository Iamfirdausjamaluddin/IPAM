"""
Pydantic schemas for the IPAM API.

These define the SHAPE of data crossing the API boundary — what clients
send in (requests) and what the API sends back (responses). They are
deliberately separate from the SQLAlchemy models in models.py:

  - models.py describes how data is STORED (database tables).
  - schemas.py describes how data is VALIDATED and SERIALIZED (the API).

The same field can have different rules in each. For example, created_at
is required on the way OUT (the DB always has it) but must NOT be sent
on the way IN (the DB fills it in automatically).
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReservationBase(BaseModel):
    """Fields shared by create and update — all optional except where noted.

    These are the user-supplied 'intent' fields. None of them are required
    at this level because a reservation can be created as a partial stub
    (e.g. you know you want an IP but not the MAC yet).
    """

    hostname: str | None = Field(
        default=None,
        max_length=255,
        description="Hostname the user intends for this IP.",
    )
    vm_id: int | None = Field(
        default=None,
        description="Proxmox VM ID (700-799 for this project). Null if not a VM.",
    )
    mac_address: str | None = Field(
        default=None,
        max_length=17,
        description="MAC address in XX:XX:XX:XX:XX:XX format.",
    )
    reserved_by: str | None = Field(
        default=None,
        max_length=255,
        description="Who reserved this IP (free text for now).",
    )
    note: str | None = Field(
        default=None,
        description="Free-form note about this reservation.",
    )


class ReservationCreate(ReservationBase):
    """Request body for POST /reservations.

    Inherits the optional fields from ReservationBase and ADDS the required
    ip field. ip is required because you cannot create a reservation without
    saying which IP it's for. Timestamps are intentionally absent — the
    database sets created_at and updated_at itself.
    """

    ip: str = Field(
        ...,
        max_length=45,
        description="The IP address being reserved (e.g. 10.10.14.50).",
    )


class ReservationUpdate(ReservationBase):
    """Request body for PUT /reservations/{ip}.

    Identical to ReservationBase: every field is optional. This lets a
    client send only the fields they want to change (e.g. just the note)
    without having to resend the whole record. ip is NOT here because it
    comes from the URL path, not the body — and you can't change an IP's
    identity by editing it; you'd delete and recreate instead.
    """

    pass


class ReservationRead(ReservationBase):
    """Response body returned by all reservation endpoints.

    Includes everything the database knows: the ip, all the intent fields
    (inherited from ReservationBase), and the server-managed timestamps.

    model_config with from_attributes=True is the Pydantic v2 setting that
    lets FastAPI build this schema directly from a SQLAlchemy Reservation
    object (reading row.ip, row.hostname, etc.) instead of requiring a dict.
    Without it, FastAPI wouldn't know how to turn a DB row into JSON.
    """

    model_config = ConfigDict(from_attributes=True)

    ip: str
    created_at: datetime
    updated_at: datetime