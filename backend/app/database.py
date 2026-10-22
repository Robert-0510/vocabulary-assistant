"""SQLAlchemy 引擎与会话。"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import config

engine = create_engine(
    config.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    # 健康检查/启动失败时不要长时间卡住（PyMySQL 参数）
    connect_args={"connect_timeout": 5},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
