"""Markdown 词书解析。

支持的表格格式（表头与分隔行自动跳过，例句列可留空）：
| 单词 | 音标 | 释义 | 例句 |
"""

import re

_CJK = re.compile(r"[一-鿿]")
_SEPARATOR_CELL = re.compile(r"^:?-{2,}:?$")
_HEADER_HINTS = {"单词", "音标", "释义", "例句", "word", "phonetic", "meaning", "example"}
_MD_MARKS = re.compile(r"\*+")

# 与数据库列宽保持一致，避免超长输入触发 MySQL DataError（500）。
MAX_BOOK_NAME = 100
MAX_SPELLING = 100
MAX_PHONETIC = 200
MAX_DEFINITION = 1000
MAX_EXAMPLE_EN = 2000
MAX_EXAMPLE_CN = 500


def _clip(value: str, limit: int) -> str:
    """按字符截断到数据库可容纳的长度。"""
    return (value or "")[:limit].strip()


def split_example(raw: str) -> tuple[str, str]:
    """把例句按第一个中文字符拆成（英文, 中文）。"""
    raw = (raw or "").strip()
    if not raw:
        return "", ""
    m = _CJK.search(raw)
    if not m:
        return raw, ""
    return raw[: m.start()].rstrip(), raw[m.start() :].strip()


def _is_separator_row(cells: list[str]) -> bool:
    non_empty = [c for c in cells if c]
    return bool(non_empty) and all(_SEPARATOR_CELL.match(c) for c in non_empty)


def _looks_like_header(cells: list[str]) -> bool:
    """无分隔线的表格兜底：至少两格精确命中表头词才认为是表头。

    只做精确匹配，避免例句/释义中恰好出现 "word" 等子串时误删数据行。
    """
    hits = sum(1 for c in cells if c.strip().lower() in _HEADER_HINTS)
    return hits >= 2


def _table_rows(content: str) -> list[list[str]]:
    """按表格分块收集数据行，并跳过表头 / 分隔线。"""
    blocks: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if cells:
                current.append(cells)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)

    rows: list[list[str]] = []
    for block in blocks:
        # Markdown 表格中，分隔线正上方的一行是表头。
        header_indexes = {
            i - 1 for i, cells in enumerate(block) if i > 0 and _is_separator_row(cells)
        }
        block_rows = [c for c in block if not _is_separator_row(c)]
        has_separator = len(block_rows) != len(block)
        first_data_index = next(
            (i for i, cells in enumerate(block) if not _is_separator_row(cells)), None
        )

        for i, cells in enumerate(block):
            if i in header_indexes or _is_separator_row(cells):
                continue
            # 没有分隔线的自造表格：只对首行做精确表头判断
            if not has_separator and i == first_data_index and _looks_like_header(cells):
                continue
            rows.append(cells)
    return rows


def parse_markdown(content: str) -> tuple[str, list[dict], int]:
    """解析 Markdown 文本。

    返回 (词书名, 单词列表, 跳过数)。单词字段：
    spelling / phonetic / definition / example_en / example_cn / seq
    """
    name = ""
    for line in content.splitlines():
        stripped = line.strip()
        if not name and stripped.startswith("# ") and "|" not in stripped:
            candidate = _MD_MARKS.sub("", stripped[2:]).strip()
            if candidate:
                name = _clip(candidate, MAX_BOOK_NAME)

    words: list[dict] = []
    seen: set[str] = set()
    skipped = 0
    for cells in _table_rows(content):
        cells = [_MD_MARKS.sub("", c).strip() for c in cells]
        spelling = _clip(cells[0], MAX_SPELLING)
        definition = _clip(cells[2], MAX_DEFINITION) if len(cells) > 2 else ""
        if not spelling or not definition:
            skipped += 1
            continue
        key = spelling.lower()
        if key in seen:  # 文件内去重
            skipped += 1
            continue
        seen.add(key)
        phonetic = _clip(cells[1], MAX_PHONETIC) if len(cells) > 1 else ""
        example_raw = cells[3] if len(cells) > 3 else ""
        example_en, example_cn = split_example(example_raw)
        words.append(
            {
                "spelling": spelling,
                "phonetic": phonetic,
                "definition": definition,
                "example_en": _clip(example_en, MAX_EXAMPLE_EN) or None,
                "example_cn": _clip(example_cn, MAX_EXAMPLE_CN) or None,
                "seq": len(words),
            }
        )
    return name, words, skipped
