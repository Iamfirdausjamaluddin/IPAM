"""
SQLAlchemy ORM models for the IPAM backend.

Each class here describes one database table. Alembic reads these to
generate migrations, and the application code uses them to query and
modify rows as Python objects.
"""
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class IPAddress(Base):
    """One row per IP address tracked by the IPAM."""

    __tablename__ = "ip_addresses"

    # Primary key — auto-incrementing integer assigned by Postgres.
    # Every row needs a unique, stable identifier; this is the standard.
    id: Mapped[int] = mapped_column(primary_key=True)

    # The IP itself, stored as a string for now (e.g. "10.10.14.10").
    # unique=True means Postgres will reject duplicate IPs at the DB level,
    # so two pieces of code can't accidentally create the same IP twice.
    # index=True speeds up lookups by IP (the most common query).
    ip: Mapped[str] = mapped_column(String(45), unique=True, index=True)

    # The IPAM status: gateway / in_use / reserved / free / rogue.
    # We'll tighten this to an Enum in a later phase; String is fine for now.
    status: Mapped[str] = mapped_column(String(32))

    # Hostname. Optional — a 'free' IP has no hostname yet, so this is nullable.
    # Optional[str] in the type hint signals nullability to SQLAlchemy.
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Whether the IP responded to the last ping. Defaults to False so newly
    # inserted rows have a sane starting value before the scanner runs.
    is_alive: Mapped[bool] = mapped_column(Boolean, default=False)

    # Last time this IP responded to a ping. NULL means we've never seen it
    # respond. Only the scanner writes here, and only on a successful ping.
    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamps — set by the database, not by our Python code.
    # server_default=func.now() tells Postgres to fill it in on INSERT.
    # onupdate=func.now() updates it whenever the row is modified.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<IPAddress(id={self.id}, ip={self.ip!r}, status={self.status!r})>"