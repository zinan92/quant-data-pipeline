from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from src.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    connect_args={
        "check_same_thread": False,
        "timeout": 30,  # 增加锁等待超时时间到30秒
    }
    if settings.database_url.startswith("sqlite")
    else {},
    pool_size=20,  # 增加连接池大小
    max_overflow=10,  # 允许额外10个连接
    pool_pre_ping=True,  # 每次连接前检查连接有效性
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)

Base = declarative_base()


# 为SQLite启用WAL模式以提高并发性能
if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=10000")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope for database operations."""
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create database tables if they do not yet exist."""
    from src import models  # noqa: F401  # ensure model metadata is registered

    Base.metadata.create_all(bind=engine)
