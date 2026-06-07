"""
Database connection setup for the IPAM backend.

Now reads configuration from the central Settings object (config.py) instead
of calling os.getenv / load_dotenv directly. The connection details live in
one place, validated and typed, so the same code runs unchanged on the laptop
and inside a container.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import settings

# Kept as a module-level name for backward compatibility. Anything that did
# `from database import DATABASE_URL` (most likely Alembic's env.py) keeps
# working without edits. We'll confirm Alembic in Phase 5.2.
DATABASE_URL = settings.database_url

# The engine is a connection pool to Postgres — created once, reused for the
# lifetime of the app. settings.sql_echo (set SQL_ECHO=true in .env) logs
# every SQL statement to the terminal, which is helpful while learning.
engine = create_engine(DATABASE_URL, echo=settings.sql_echo)

# SessionLocal is a factory: calling SessionLocal() gives a fresh Session,
# the object we use to run queries and save changes.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# Base is the parent class for every ORM model we define. SQLAlchemy uses it
# to collect table definitions in one registry.
class Base(DeclarativeBase):
    pass