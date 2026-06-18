import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.settings import get_settings

# 默认 SQLite，如果想换 PostgreSQL 或 MySQL，可以直接改 .env
settings = get_settings()
DATABASE_URL = settings.database_url

# SQLite 需要特定连接参数，其他数据库不需要
engine_args = {}
if DATABASE_URL.startswith("sqlite"):
    engine_args["connect_args"] = {"check_same_thread": False}

_pool_args = {}
if not DATABASE_URL.startswith("sqlite"):
    _pool_args = {
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_pre_ping": True,
    }

engine = create_engine(
    DATABASE_URL,
    echo=settings.sqlalchemy_echo,
    **engine_args,
    **_pool_args,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_engine():
    return engine


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
