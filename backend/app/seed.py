"""启动初始化：自动建库、迁移表结构、保证设置行存在。"""

import re

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import config
from app.database import engine
from app.migrations import run_migrations
from app.models import AppSetting


def ensure_database_exists() -> None:
    """数据库不存在时自动创建（账号需具备 CREATE 权限）。"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return
    except OperationalError as exc:
        code = getattr(exc.orig, "args", (None,))[0]
        if code != 1049:  # 1049 = Unknown database
            raise

    url = make_url(config.database_url)
    dbname = url.database or ""
    if not re.fullmatch(r"[A-Za-z0-9_]+", dbname):
        raise RuntimeError(f"数据库名不合法：{dbname!r}")

    # 注意：URL.set(database=None) 表示「不修改」，必须显式设为空串才能去掉库名
    server_url = url.set(database="")
    bootstrap = create_engine(server_url, pool_pre_ping=True)
    try:
        with bootstrap.begin() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{dbname}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
    finally:
        bootstrap.dispose()


def ensure_settings(db: Session, user_id: int) -> AppSetting:
    """取得（必要时创建）某个账号的每日任务配置。"""
    s = db.get(AppSetting, user_id)
    if s is None:
        s = AppSetting(user_id=user_id)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def init_db() -> None:
    import app.models  # noqa: F401  确保模型注册到 Base

    ensure_database_exists()
    run_migrations()
