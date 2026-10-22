"""生成发布压缩包（源码包或含 exe 的运行包）。

用法：
    python scripts/package_release.py                # 源码包
    python scripts/package_release.py --with-exe     # 源码 + backend/dist 下的 exe

产物写入 release/，并输出 SHA-256。脚本会拒绝包含 .env、构建产物或版权资料。
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE_DIR = ROOT / "release"

EXCLUDE_DIRS = {
    ".git",
    ".github",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".idea",
    ".vscode",
    "release",
    "coverage",
    "htmlcov",
    "_local_only",
    "private",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".log", ".spec"}
EXCLUDE_FILES = {
    "frontend/src/components.d.ts",
    "frontend/tsconfig.tsbuildinfo",
}
FORBIDDEN_NAMES = ("GRE阅读", "机经", "extract_gre_pdf")


def app_version() -> str:
    text = (ROOT / "backend" / "app" / "version.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not match:
        raise SystemExit("无法从 backend/app/version.py 读取版本号")
    return match.group(1)


def iter_release_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if rel.as_posix() in EXCLUDE_FILES:
            continue
        name = path.name
        if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
            continue
        if any(part in rel.as_posix() for part in FORBIDDEN_NAMES):
            continue
        if path.suffix.lower() in EXCLUDE_SUFFIXES:
            continue
        if rel.parts[0] == "backend" and path.suffix.lower() in {".exe", ".dll"}:
            continue
        files.append(path)
    return files


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-exe", action="store_true", help="同时打包已构建的 exe")
    args = parser.parse_args()

    version = app_version()
    RELEASE_DIR.mkdir(exist_ok=True)
    suffix = "win64" if args.with_exe else "source"
    archive = RELEASE_DIR / f"vocabulary-assistant-{version}-{suffix}.zip"
    prefix = f"vocabulary-assistant-{version}"

    files = iter_release_files()

    exe = ROOT / "backend" / "dist" / "背单词助手.exe"
    if args.with_exe and not exe.is_file():
        raise SystemExit(f"未找到 {exe}，请先运行 build_exe.bat")

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, f"{prefix}/{path.relative_to(ROOT).as_posix()}")
        if args.with_exe:
            zf.write(exe, f"{prefix}/背单词助手-{version}.exe")

    print(f"已生成：{archive}")
    print(f"SHA-256：{sha256(archive)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
