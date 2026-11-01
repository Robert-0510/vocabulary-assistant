"""测试夹具：API 测试使用独立的临时 MySQL 数据库，绝不触碰真实库。"""

import os
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _skip_or_fail(message: str) -> None:
    """本地没有 MySQL 时跳过；CI 中必须失败，避免假绿。"""
    if os.environ.get("CI"):
        pytest.fail(f"CI 环境数据库不可用：{message}")
    pytest.skip(message)


def _read_dotenv() -> dict[str, str]:
    env: dict[str, str] = {}
    path = BACKEND_DIR / ".env"
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


@pytest.fixture(scope="session")
def api_client():
    """启动 FastAPI + 临时数据库；MySQL 不可用时自动跳过 API 测试。"""
    dotenv = _read_dotenv()
    host = os.environ.get("DB_HOST", dotenv.get("DB_HOST", "127.0.0.1"))
    port = int(os.environ.get("DB_PORT", dotenv.get("DB_PORT", "3306")))
    user = os.environ.get("DB_USER", dotenv.get("DB_USER", "root"))
    password = os.environ.get("DB_PASSWORD", dotenv.get("DB_PASSWORD", ""))
    db_name = f"vocab_test_{uuid.uuid4().hex[:10]}"

    try:
        import pymysql

        conn = pymysql.connect(
            host=host, port=port, user=user, password=password, charset="utf8mb4"
        )
    except Exception as exc:  # noqa: BLE001
        _skip_or_fail(f"MySQL 不可用，跳过 API 测试：{exc}")

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    except Exception as exc:  # noqa: BLE001
        conn.close()
        _skip_or_fail(f"无法创建临时测试库，跳过 API 测试：{exc}")
    conn.close()

    # 必须在导入 app 之前设置，pydantic-settings 的环境变量优先级高于 .env
    os.environ.update(
        DB_HOST=host,
        DB_PORT=str(port),
        DB_USER=user,
        DB_PASSWORD=password,
        DB_NAME=db_name,
        # 测试会连续注册多个账号，关闭限流避免相互干扰；限流逻辑单独做单元测试。
        RATE_LIMIT_ENABLED="false",
    )

    from fastapi.testclient import TestClient

    from app.database import engine
    from app.main import app

    try:
        with TestClient(app) as client:
            yield client
    finally:
        engine.dispose()
        conn = pymysql.connect(
            host=host, port=port, user=user, password=password, charset="utf8mb4"
        )
        try:
            with conn.cursor() as cur:
                cur.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
        finally:
            conn.close()


@pytest.fixture()
def auth_client(api_client):
    """注册并登录一个独立测试账号，测试结束后退出，避免污染其他用例。"""
    username = f"user_{uuid.uuid4().hex[:10]}"
    resp = api_client.post(
        "/api/auth/register",
        json={"username": username, "password": "password123"},
    )
    assert resp.status_code == 200, resp.text
    yield api_client
    api_client.post("/api/auth/logout")
    api_client.cookies.clear()
