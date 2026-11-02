# -*- coding: utf-8 -*-
"""构建 Windows 单文件 exe（替代已删除的 build_exe.bat）。

步骤与原 bat 一致：
1) 安装后端构建依赖（requirements-build.txt）
2) 构建前端（npm ci / npm run build）
3) PyInstaller 打包 launcher.py
4) 复制许可与说明到 dist，并打印 SHA-256

用法：
    backend\\.venv\\Scripts\\python.exe scripts\\build_exe.py
    backend\\.venv\\Scripts\\python.exe scripts\\build_exe.py --skip-install --skip-frontend
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV_PY = BACKEND / ".venv" / "Scripts" / "python.exe"
DIST = BACKEND / "dist"
APP_NAME = "背单词助手"

COPY_FILES = [
    (ROOT / "LICENSE", DIST / "LICENSE"),
    (ROOT / "README.md", DIST / "README.md"),
    (ROOT / "LICENSES" / "THIRD_PARTY_NOTICES.md", DIST / "THIRD_PARTY_NOTICES.md"),
    (ROOT / "docs" / "legal" / "PRIVACY.md", DIST / "PRIVACY.md"),
    (ROOT / "CHANGELOG.md", DIST / "CHANGELOG.md"),
]


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="构建背单词助手 exe")
    parser.add_argument("--skip-install", action="store_true", help="跳过 pip install")
    parser.add_argument("--skip-frontend", action="store_true", help="跳过 npm 构建")
    args = parser.parse_args(argv[1:])

    python = str(VENV_PY if VENV_PY.exists() else Path(sys.executable))
    if not VENV_PY.exists():
        print(f"提示：未找到 {VENV_PY}，将使用当前解释器 {python}")

    if not args.skip_install:
        print("[1/4] 安装构建依赖…")
        run([python, "-m", "pip", "install", "--quiet", "-r", str(BACKEND / "requirements-build.txt")])

    if not args.skip_frontend:
        print("[2/4] 构建前端…")
        if not (FRONTEND / "node_modules").exists():
            run(["npm", "ci"], cwd=FRONTEND)
        run(["npm", "run", "build"], cwd=FRONTEND)

    print("[3/4] PyInstaller 打包…")
    pyinstaller = BACKEND / ".venv" / "Scripts" / "pyinstaller.exe"
    exe = str(pyinstaller if pyinstaller.exists() else Path(python).with_name("pyinstaller.exe"))
    run([
        exe, "--onefile", "--clean", "--noconfirm", "--name", APP_NAME,
        "--icon", str(ROOT / "assets" / "app.ico"),
        "--version-file", str(ROOT / "assets" / "version_info.txt"),
        "--paths", str(BACKEND),
        "--add-data", f"{FRONTEND / 'dist'};app_static",
        "--hidden-import", "app.main",
        "--hidden-import", "app.routers.backup",
        "--hidden-import", "sqlalchemy.dialects.mysql.pymysql",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "uvicorn.lifespan.on",
        "--hidden-import", "fsrs",
        str(ROOT / "launcher.py"),
    ], cwd=BACKEND)

    print("[4/4] 复制许可与说明…")
    for src, dst in COPY_FILES:
        if src.exists():
            shutil.copy2(src, dst)
        else:
            print(f"警告：缺少 {src.name}")

    target = DIST / f"{APP_NAME}.exe"
    if target.exists():
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        print(f"\n构建完成：{target}")
        print(f"SHA-256: {digest}")
        return 0
    print(f"未找到产物 {target}，打包可能失败", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
