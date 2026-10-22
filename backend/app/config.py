"""应用配置：从 .env 读取数据库连接信息。"""

import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


def env_file_path() -> Path:
    """定位 .env，不依赖进程当前工作目录。

    优先级：
    1. VOCAB_ENV_FILE 环境变量（启动器/测试可显式指定）
    2. 冻结模式（exe）：exe 同目录的旧版 .env > %APPDATA%\\背单词助手\\.env
    3. 源码模式：backend/.env
    """
    override = os.environ.get("VOCAB_ENV_FILE")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        local_env = Path(sys.executable).resolve().parent / ".env"
        if local_env.exists():
            return local_env
        appdata = Path(os.environ.get("APPDATA") or Path.home())
        return appdata / "背单词助手" / ".env"
    return Path(__file__).resolve().parent.parent / ".env"


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(env_file_path()), env_file_encoding="utf-8")

    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "vocab_assistant"
    # 逗号分隔；留空则完全不启用 CORS。开发时 Vite 已代理 /api，通常无需跨域。
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---------- 上传 / 导入边界 ----------
    MAX_UPLOAD_MB: int = 10
    MAX_IMPORT_MB: int = 50
    MAX_WORDS_PER_BOOK: int = 20_000

    # ---------- 会话 ----------
    SESSION_TTL_DAYS: int = 30
    # 放在 HTTPS 反向代理后时设为 true；本地 http://127.0.0.1 保持 false。
    COOKIE_SECURE: bool = False

    # ---------- 登录限流 ----------
    RATE_LIMIT_ENABLED: bool = True
    LOGIN_RATE_LIMIT: int = 10  # 每 60 秒，按 IP + 用户名
    REGISTER_RATE_LIMIT: int = 10  # 每 3600 秒，按 IP
    PASSWORD_RATE_LIMIT: int = 5  # 每 600 秒，按账号

    @property
    def database_url(self) -> str:
        pwd = quote_plus(self.DB_PASSWORD)
        return (
            f"mysql+pymysql://{self.DB_USER}:{pwd}@{self.DB_HOST}:{self.DB_PORT}"
            f"/{self.DB_NAME}?charset=utf8mb4"
        )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


config = AppConfig()
