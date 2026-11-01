"""把一套真题（questions.pdf + answers.xlsx）导入成结构化派生数据。

只做文件 → JSON，不连数据库、不联网。产物落在 <session>/derived/ 下：
    answers.json   规范化答案（字母已映射成单词）
    edges.json     由答案推导的等价对（同一题的两个答案 = 1 条强证据）
    ../manifest.json  元数据（文件哈希、题数、状态）

PDF 解析是独立的一步：本脚本只消费 <session>/derived/items.json。
没有 items.json 时，答案必须是单词（不能是字母）。

用法：
    python scripts/import_exam.py private/exams/<session-id>
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

try:
    from openpyxl import load_workbook
except ImportError:  # pragma: no cover
    print("缺少 openpyxl：pip install -r backend/requirements-import.txt", file=sys.stderr)
    raise SystemExit(2) from None

LETTER = re.compile(r"^[A-Fa-f]$")


def norm_word(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip().strip(".,;:")
    return text.lower()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_answers(path: Path) -> list[dict]:
    wb = load_workbook(path, data_only=True, read_only=True)
    ws = wb["answers"] if "answers" in wb.sheetnames else wb[wb.sheetnames[0]]
    head = [
        str(c.value).strip() if c.value is not None else ""
        for c in next(ws.iter_rows(min_row=1, max_row=1))
    ]
    idx = {name: i for i, name in enumerate(head)}
    for required in ("题号", "答案A", "答案B"):
        if required not in idx:
            raise SystemExit(f"[错误] 表头缺少列 {required}；当前表头 = {head}")

    out = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not any(v is not None and str(v).strip() for v in row):
            continue
        no = str(row[idx["题号"]]).strip()
        a = str(row[idx["答案A"]]).strip() if row[idx["答案A"]] is not None else ""
        b = str(row[idx["答案B"]]).strip() if row[idx["答案B"]] is not None else ""
        if not no or not a or not b:
            raise SystemExit(f"[错误] 题号 {no or '?'} 的答案不完整")
        out.append({"no": no, "a": a, "b": b})
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 1

    session_dir = Path(argv[1]).resolve()
    if not session_dir.is_dir():
        print(f"[错误] 不是目录：{session_dir}")
        return 1
    session = session_dir.name

    answer_file = session_dir / "answers.xlsx"
    if not answer_file.exists():
        print(f"[错误] 缺少 answers.xlsx：{answer_file}")
        return 1

    derived = session_dir / "derived"
    derived.mkdir(exist_ok=True)

    # 可选：PDF 解析产物，用于字母 → 单词
    option_maps: dict[str, dict[str, str]] = {}
    items_file = derived / "items.json"
    if items_file.exists():
        payload = json.loads(items_file.read_text(encoding="utf-8"))
        for item in payload.get("items", []):
            option_maps[str(item["no"]).strip()] = {
                k.upper(): norm_word(v) for k, v in item.get("options", {}).items()
            }

    raw = read_answers(answer_file)
    resolved, problems = [], []
    for row in raw:
        no, a, b = row["no"], row["a"], row["b"]
        mapping = option_maps.get(no)
        pair = []
        for value in (a, b):
            if LETTER.match(value):
                if not mapping:
                    problems.append(
                        f"题号 {no}：答案 {value} 是字母，但缺少 derived/items.json，无法映射"
                    )
                    break
                word = mapping.get(value.upper())
                if not word:
                    problems.append(f"题号 {no}：选项 {value} 在 items.json 里找不到")
                    break
                pair.append(word)
            else:
                pair.append(norm_word(value))
        if len(pair) != 2:
            continue
        x, y = sorted(pair)
        if x == y:
            problems.append(f"题号 {no}：两个答案相同（{x}）")
            continue
        resolved.append({"no": no, "a": x, "b": y})

    if problems:
        for p in problems[:30]:
            print(f"[错误] {p}")
        print(f"共 {len(problems)} 个问题，未写出任何文件")
        return 1

    # 边：同一题的两个答案
    edges, seen = [], {}
    for row in resolved:
        key = (row["a"], row["b"])
        seen[key] = seen.get(key, 0) + 1
        edges.append({"a": row["a"], "b": row["b"], "item_no": row["no"], "evidence": "exam"})

    (derived / "answers.json").write_text(
        json.dumps({"session": session, "items": resolved}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (derived / "edges.json").write_text(
        json.dumps(
            {"session": session, "evidence": "exam", "trust": "strong", "edges": edges},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    files = {"answers.xlsx": {"sha256": sha256(answer_file), "bytes": answer_file.stat().st_size}}
    qpdf = session_dir / "questions.pdf"
    if qpdf.exists():
        files["questions.pdf"] = {"sha256": sha256(qpdf), "bytes": qpdf.stat().st_size}

    manifest = {
        "session": session,
        "status": "parsed",
        "parsed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "files": files,
        "counts": {
            "items": len(resolved),
            "edges": len(edges),
            "unique_pairs": len(seen),
            "repeated_pairs": sum(1 for n in seen.values() if n > 1),
        },
    }
    (session_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"session：{session}")
    print(
        f"  题目 {len(resolved)} 道；等价边 {len(edges)} 条；唯一词对 {len(seen)}；重复出现 {manifest['counts']['repeated_pairs']} 对"
    )
    print(f"  产物：{derived}（answers.json / edges.json）+ manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
