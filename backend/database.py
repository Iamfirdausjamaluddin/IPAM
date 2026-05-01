"""
Database connection setup for the IPAM backend.

Builds the SQLAlchemy engine from DATABASE_URL in .env, exposes a
SessionLocal factory for short-lived DB sessions, and a Base class
that all ORM models will inherit from.
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Load variables from .env into os.environ.
# Must run before we try to read DATABASE_URL.
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Did you create backend/.env?"
    )

# The engine is a connection pool to Postgres — created once, reused
# for the lifetime of the app. echo=True logs every SQL statement to
# the terminal, which is enormously helpful while learning.
# echo defaults to False; set SQL_ECHO=true in .env to see SQL traffic.
SQL_ECHO = os.getenv("SQL_ECHO", "false").lower() == "true"
engine = create_engine(DATABASE_URL, echo=SQL_ECHO)

# SessionLocal is a factory: calling SessionLocal() gives a fresh
# Session, the object we use to run queries and save changes.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Base is the parent class for every ORM model we will define.
# SQLAlchemy uses it to collect table definitions in one registry.
class Base(DeclarativeBase):
    pass