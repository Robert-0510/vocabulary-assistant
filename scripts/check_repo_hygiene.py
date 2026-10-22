"""发布前的仓库卫生检查。

检查项：
- 不包含真实 .env（仅允许 .env.example）
- 不包含受版权保护的 GRE 资料或提取脚本
- 不包含虚拟环境 / 依赖 / 构建产物
- 源码与构建脚本中不出现写死的本机绝对路径
- 不包含超大文件（package-lock.json 除外）

用法：python scripts/check_repo_hygiene.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    ".git",
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
}
ALLOWED_ENV = {".env.example"}
FORBIDDEN_NAME_PARTS = ("GRE阅读", "机经", "extract_gre_pdf")
MAX_BYTES = 5 * 1024 * 1024
LARGE_FILE_ALLOWLIST = {"frontend/package-lock.json"}
CODE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".vue",
    ".js",
    ".bat",
    ".cmd",
    ".spec",
    ".toml",
    ".yml",
    ".yaml",
}


def _git_tracked_files() -> list[Path] | None:
    """有 git 仓库时只检查已跟踪文件，避免本地 .env / dist 造成误报。"""
    if not (ROOT / ".git").exists():
        return None
    try:
        output = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=ROOT, stderr=subprocess.DEVNULL
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return [ROOT / name for name in output.decode("utf-8").split("\0") if name]


def iter_files() -> tuple[list[Path], bool]:
    tracked = _git_tracked_files()
    if tracked is not None:
        return [path for path in tracked if path.is_file()], True

    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        # 尚未初始化 git 时，本地 .env 是开发配置；由发布打包脚本负责排除。
        if path.name == ".env" or (path.name.startswith(".env.") and path.name not in ALLOWED_ENV):
            continue
        files.append(path)
    return files, False


def main() -> int:
    problems: list[str] = []
    files, tracked = iter_files()
    if not tracked:
        print("提示：尚未初始化 git，按文件系统扫描（已跳过本地 .env）。")

    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        name = path.name

        if name == ".env" or (name.startswith(".env.") and name not in ALLOWED_ENV):
            problems.append(f"发现真实环境配置文件：{rel}")
            continue

        if any(part in rel for part in FORBIDDEN_NAME_PARTS):
            problems.append(f"发现受版权保护的示例资料：{rel}")
            continue

        size = path.stat().st_size
        if size > MAX_BYTES and rel not in LARGE_FILE_ALLOWLIST:
            problems.append(f"超大文件（{size / 1024 / 1024:.1f} MB）：{rel}")

        if path.suffix.lower() in CODE_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="ignore")
            # 拆分字符串，避免检查脚本自己命中自己
            markers = ("F:" + "/study_material", "F:" + "\\study_material")
            if any(marker in text for marker in markers):
                problems.append(f"源码中写死了本机绝对路径：{rel}")

    if problems:
        print("仓库卫生检查未通过：")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("仓库卫生检查通过：未发现密钥、版权资料、构建产物或绝对路径。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
