"""
Database session management.
Provides SQLAlchemy engine and session factory.

OPTIMIZATIONS (v2):
- Proper exception handling with rollback in get_db()
- Connection pool tuning for concurrent API access
- SQLite WAL mode + MMAP for read performance
- Query timeout safeguards
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool, StaticPool, QueuePool
from typing import Generator
import logging

from app.core.config import get_settings

logger = logging.getLogger("app.db")

settings = get_settings()

# Get Database URL
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# Fix for Render/PostgreSQL: SQLAlchemy 1.4+ removed support for 'postgres://'
if SQLALCHEMY_DATABASE_URL and SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Handle SQLite vs PostgreSQL connection args
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    is_in_memory_sqlite = (
        SQLALCHEMY_DATABASE_URL in {"sqlite://", "sqlite:///:memory:"}
        or SQLALCHEMY_DATABASE_URL.endswith(":memory:")
    )

    # File-based SQLite should not use StaticPool in concurrent API usage.
    # QueuePool significantly improves concurrent API performance.
    sqlite_pool = StaticPool if is_in_memory_sqlite else QueuePool

    connect_args = {"check_same_thread": False}
    pool_kwargs = {}
    
    if not is_in_memory_sqlite:
        # Increase timeout to prevent locking errors and use connection pooling
        connect_args["timeout"] = 30.0
        pool_kwargs = {
            "pool_size": 20,
            "max_overflow": 30,
            "pool_timeout": 60.0,
            "pool_recycle": 1800,    # Recycle connections every 30 minutes
            "pool_pre_ping": True,   # Verify connections before use
        }

    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args=connect_args,
        poolclass=sqlite_pool,
        **pool_kwargs
    )
    
    # Enable performance and Foreign Key support in SQLite
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    
    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        # Check if we are using SQLite using the connection string
        if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")       # WAL mode for concurrent reads
            cursor.execute("PRAGMA synchronous=NORMAL")     # Faster writes, still safe
            cursor.execute("PRAGMA cache_size=-64000")      # 64MB cache (was 8MB)
            cursor.execute("PRAGMA temp_store=MEMORY")      # Temp tables in memory
            cursor.execute("PRAGMA mmap_size=3000000000")   # Mmap for much faster reads
            cursor.execute("PRAGMA busy_timeout=30000")     # Wait 30s for lock
            cursor.execute("PRAGMA wal_autocheckpoint=1000") # Auto-checkpoint WAL
            cursor.close()
else:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_size=20,
        max_overflow=30,
        pool_timeout=60,
        pool_recycle=1800,
        pool_pre_ping=True,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for getting database sessions.
    
    IMPORTANT: Includes proper rollback on exception to prevent
    connection leaks and stale transaction state.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
