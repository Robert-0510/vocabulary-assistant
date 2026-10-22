"""FastAPI 入口。启动：uvicorn app.main:app --reload --port 8000"""

import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import config
from app.database import engine
from app.routers import auth, backup, books, settings, stats, study
from app.seed import init_db
from app.version import __version__

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("app")


def _frontend_dist() -> Path | None:
    """前端构建产物目录：环境变量 > 源码运行 frontend/dist > PyInstaller 冻结 app_static。"""
    env = os.environ.get("FRONTEND_DIST")
    if env:
        p = Path(env)
        return p if p.is_dir() else None
    if getattr(sys, "frozen", False):  # PyInstaller 打包后的 exe
        p = Path(getattr(sys, "_MEIPASS", "")) / "app_static"
        return p if p.is_dir() else None
    p = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    return p if p.is_dir() else None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()  # 自动建表 + 初始化设置行
    yield


app = FastAPI(title="背单词助手 API", version=__version__, lifespan=lifespan)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    """记录请求耗时与状态码；不记录请求体，避免泄露密码/词书内容。"""
    request_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed = (time.perf_counter() - started) * 1000
        logger.exception(
            "%s %s -> 500 %.1fms request_id=%s",
            request.method,
            request.url.path,
            elapsed,
            request_id,
        )
        raise
    elapsed = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    # 静态资源只在 DEBUG 级别记录，避免启动/刷新时刷屏
    log_level = logging.INFO if request.url.path.startswith("/api/") else logging.DEBUG
    logger.log(
        log_level,
        "%s %s -> %s %.1fms request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed,
        request_id,
    )
    return response


# 仅在源码开发模式启用跨域，且只允许本机开发地址；
# 冻结版由同一端口托管前端，属于同源请求，完全不需要 CORS。
if not getattr(sys, "frozen", False) and config.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(backup.router)
app.include_router(books.router)
app.include_router(study.router)
app.include_router(stats.router)
app.include_router(settings.router)


@app.get("/api/health")
def health():
    """就绪探测：同时检查数据库连接，数据库不可用时返回 503。"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - 健康检查需要吞掉底层异常
        logger.warning("health check failed: %s", exc)
        raise HTTPException(503, "数据库不可用") from exc
    return {"ok": True, "db": "ok", "version": __version__}


# ---------- 生产模式：托管前端 SPA（必须注册在所有 API 路由之后） ----------
_DIST = _frontend_dist()
if _DIST is not None:
    _DIST_ROOT = _DIST.resolve()
    _ASSETS = _DIST / "assets"
    if _ASSETS.is_dir():
        app.mount("/assets", StaticFiles(directory=_ASSETS), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(404, "接口不存在")
        candidate = (_DIST / full_path).resolve()
        # 真实文件直接返回，其余一律回退 index.html（SPA history 路由）
        if full_path and candidate.is_file() and candidate.is_relative_to(_DIST_ROOT):
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")
else:
    print("[提示] 未找到前端构建产物（frontend/dist），仅提供 API 服务；请先 npm run build")
