"""
Shared types for the scanner subsystem.

Lives in its own module so scanner.py and db_writer.py can both import
from it without importing each other (which would create a circular
import). A 'neutral' module like this is the standard fix when two
modules need to share a type but should otherwise be independent.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PingResult:
    """Outcome of pinging a single IP."""
    ip: str
    is_alive: bool