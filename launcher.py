"""一键启动器：拉起 FastAPI（同进程线程）→ 就绪后自动打开浏览器。

用法：
- 源码运行：backend\\.venv\\Scripts\\python.exe launcher.py（或直接双击 run.bat）
- 打包后的 exe：双击即用
  - 配置优先读取 exe 同目录的旧版 .env；否则使用 %APPDATA%\\背单词助手\\.env
  - 可用 VOCAB_ENV_FILE 指定配置文件，或用 VOCAB_NO_BROWSER=1 禁止自动打开浏览器
"""

import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"
HEALTH = f"{URL}/api/health"
IS_FROZEN = getattr(sys, "frozen", False)
APP_NAME = "背单词助手"

# 注意：不要在这里写任何真实凭据。首次运行生成的配置密码留空，由用户填自己的账号。
DEFAULT_ENV = (
    "DB_HOST=127.0.0.1\n"
    "DB_PORT=3306\n"
    "DB_USER=root\n"
    "DB_PASSWORD=\n"
    "DB_NAME=vocab_assistant\n"
    "# 更安全的做法是使用专用账号（见 README「数据库安全」）：\n"
    "# DB_USER=vocab_app\n"
    "# DB_PASSWORD=请填写你的密码\n"
)


def _appdata_env() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME
    return base / ".env"


def prepare_env() -> Path:
    """设置工作目录、sys.path 和 .env 位置，返回配置文件路径。"""
    if IS_FROZEN:
        exe_dir = Path(sys.executable).resolve().parent
        os.chdir(exe_dir)

        explicit = os.environ.get("VOCAB_ENV_FILE")
        legacy = exe_dir / ".env"
        if explicit:
            env_file = Path(explicit)
        elif legacy.exists():
            env_file = legacy  # 兼容旧版：配置就在 exe 旁边
        else:
            env_file = _appdata_env()

        env_file.parent.mkdir(parents=True, exist_ok=True)
        os.environ["VOCAB_ENV_FILE"] = str(env_file)

        if not env_file.exists():
            env_file.write_text(DEFAULT_ENV, encoding="utf-8")
            print(f"[背单词助手] 已生成默认配置：{env_file}")
            print("[背单词助手] 请填写 MySQL 账号密码后重新运行；数据库不存在时会尝试自动创建。")
        else:
            print(f"[背单词助手] 配置文件：{env_file}")
    else:
        root = Path(__file__).resolve().parent
        backend = root / "backend"
        os.chdir(backend)
        if str(backend) not in sys.path:
            sys.path.insert(0, str(backend))
        env_file = backend / ".env"
        if not (root / "frontend" / "dist").is_dir():
            print(
                "[背单词助手] 警告：未找到 frontend/dist，页面将无法访问，请先执行 npm run build。"
            )
    return env_file


def server_up(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(HEALTH, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def port_in_use() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((HOST, PORT)) == 0


def db_failure_hint() -> str:
    """服务线程退出时，尽量给出可执行的数据库排查结论。"""
    try:
        from sqlalchemy import text

        from app.database import engine

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - 需要展示底层驱动错误
        code = getattr(getattr(exc, "orig", None), "args", (None,))[0]
        if code == 1045:
            return "数据库账号或密码错误（1045 Access denied），请检查 .env 中的 DB_USER / DB_PASSWORD。"
        if code == 1044:
            return "当前账号无权访问该数据库（1044），请检查授权。"
        if code == 1049:
            return "数据库不存在（1049），且自动创建失败，请检查账号是否具备 CREATE 权限。"
        if code in (2002, 2003):
            return "无法连接 MySQL（2002/2003），请确认 MySQL80 服务正在运行、端口 3306 可达。"
        return f"数据库连接失败：{exc}"
    return "数据库连接正常，但服务仍未启动，请查看上方日志中的错误信息。"


def open_browser() -> None:
    if os.environ.get("VOCAB_NO_BROWSER") == "1":
        print(f"[背单词助手] 已禁用自动打开浏览器，请手动访问 {URL}")
        return
    webbrowser.open(URL)


def main() -> None:
    try:  # exe 控制台可能是 GBK 代码页，强制 UTF-8 输出避免中文乱码
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    prepare_env()

    import uvicorn

    from app.main import app as fastapi_app  # 直接导入对象，便于 PyInstaller 静态分析打包

    if server_up():
        print(f"[背单词助手] 服务已在运行，直接打开页面：{URL}")
        open_browser()
        return

    print(f"[背单词助手] 正在启动服务 {URL} …")
    server = uvicorn.Server(
        # 访问日志由 app.main 的中间件统一输出，避免重复
        uvicorn.Config(fastapi_app, host=HOST, port=PORT, log_level="info", access_log=False)
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(60):  # 最多等待 30 秒
        if server_up():
            break
        if not thread.is_alive():
            if port_in_use():
                print(f"[背单词助手] 端口 {PORT} 已被其他程序占用，请关闭占用程序后重试。")
            else:
                print(f"[背单词助手] 服务启动失败：{db_failure_hint()}")
            sys.exit(1)
        time.sleep(0.5)
    else:
        print("[背单词助手] 服务启动超时（30 秒）。")
        sys.exit(1)

    if os.environ.get("VOCAB_NO_BROWSER") == "1":
        print(f"[背单词助手] 启动成功！请手动访问 {URL}")
    else:
        print(f"[背单词助手] 启动成功！浏览器即将打开 {URL}")
    print("[背单词助手] 使用期间请保持本窗口开启；关闭本窗口或按 Ctrl+C 即可退出。")
    open_browser()

    try:
        while thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[背单词助手] 正在停止服务…")
        server.should_exit = True
        thread.join(timeout=10)
    print("[背单词助手] 已退出。")


if __name__ == "__main__":
    main()
