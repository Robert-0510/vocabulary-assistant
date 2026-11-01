"""把二部图产物导入数据库（P0）。

输入（默认在仓库 analysis/ 与 docs/audit/ 下）：
    analysis/senses.csv          1,017 个义项
    analysis/sense_edges.csv     1,148 条词对边
    analysis/review_decisions.json  26 条人工裁决
    analysis/jjci_words.json     词性 / 中文释义兜底

目标库：AppConfig.database_url（backend/.env）。

规则：
- 词书里不存在的词跳过并记日志，不自动建词；
- 义项 label_zh 优先取锚词释义的中文部分，其次词书释义、机经词释义，
  最后才回退到锚词拼写；同一 (label_zh, pos) 冲突时用锚词/成员词消歧，
  保证满足 uq_sense_book_label_pos；
- review 义项按人工裁决处理：合并 → 旧顶点 status='retired' + merged_into，
  成员与边并入锚词的主义项；拆分 → 保持拆分并置 active；
- word_senses 写入每个义项星的全部成员（成员词列 + 边的端点），
  按 (word_id, sense_id) 去重 —— 同一义项星里锚词会在多条边中重复出现；
- 只给 active 义项建 sense_states（FSRS 新卡，due=now，等待首次复习）；
- 脚本幂等：目标词书已有义项则跳过，--force 先清空该词书的图再重建。

用法：
    cd backend && python ../scripts/import_sense_graph.py
    python scripts/import_sense_graph.py --book-id 3 --force
    python scripts/import_sense_graph.py --analysis-dir analysis --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import traceback
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import AppSetting, Sense, SenseState, Word, WordBook, WordSense  # noqa: E402
from app.seed import init_db  # noqa: E402
from app.services.scheduler import utcnow_naive  # noqa: E402

DEFAULT_ANALYSIS = REPO_ROOT / "analysis"
DEFAULT_AUDIT = REPO_ROOT / "docs" / "audit" / "2026-11-02-sense-review" / "review_decisions.json"

CJK = re.compile(r"[\u4e00-\u9fff]+")
POS_PATTERN = re.compile(r"(?<![a-z])(adj|adv|verb|noun|v|n|phrase)\.", re.IGNORECASE)
POS_MAP = {
    "adj": "adj",
    "adv": "adv",
    "verb": "v",
    "noun": "n",
    "v": "v",
    "n": "n",
    "phrase": "phrase",
}
MERGED_STATUS = "retired"
ACTIVE_STATUS = "active"
NEEDS_REVIEW_STATUS = "needs_review"


@dataclass(frozen=True)
class SenseRow:
    code: str
    anchor: str
    members: tuple[str, ...]
    gloss: str
    source_status: str


@dataclass(frozen=True)
class EdgeRow:
    a: str
    b: str
    sense_code: str


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导入二部图义项数据")
    parser.add_argument("--book-id", type=int, default=None, help="目标词书 ID（默认取激活词书）")
    parser.add_argument("--force", action="store_true", help="已有义项时清空并重建")
    parser.add_argument(
        "--analysis-dir",
        type=Path,
        default=DEFAULT_ANALYSIS,
        help="存放 senses.csv / sense_edges.csv / jjci_words.json 的目录",
    )
    parser.add_argument(
        "--decisions",
        type=Path,
        default=DEFAULT_AUDIT,
        help="人工裁决 JSON（默认用归档副本）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只解析并打印统计，不写库")
    return parser.parse_args(argv)


def read_senses(path: Path) -> list[SenseRow]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: list[SenseRow] = []
        for raw in reader:
            code = (raw.get("义项ID") or "").strip()
            anchor = (raw.get("锚词") or "").strip()
            if not code or not anchor:
                continue
            members = tuple(
                part.strip() for part in (raw.get("成员词") or "").split("、") if part.strip()
            )
            rows.append(
                SenseRow(
                    code=code,
                    anchor=anchor,
                    members=members or (anchor,),
                    gloss=(raw.get("中文释义(锚词)") or "").strip(),
                    source_status=(raw.get("状态") or "auto").strip(),
                )
            )
    return rows


def read_edges(path: Path) -> list[EdgeRow]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [
            EdgeRow(
                a=(raw.get("词A") or "").strip(),
                b=(raw.get("词B") or "").strip(),
                sense_code=(raw.get("义项ID") or "").strip(),
            )
            for raw in csv.DictReader(handle)
            if (raw.get("词A") or "").strip() and (raw.get("词B") or "").strip()
        ]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def chinese_gloss(text: str) -> str:
    """抽取释义里的中文片段，拼成单个展示名（最长 120 字）。"""
    # 机经词释义里偶有「新 颖的」这类被空格拆开的中文，先去空格再抽取
    cleaned = re.sub(r"(?<=[\u4e00-\u9fff])[\s\u3000]+(?=[\u4e00-\u9fff])", "", text or "")
    parts = CJK.findall(cleaned)
    if not parts:
        return ""
    return "；".join(parts).strip("； ")[:120]


def definition_en(text: str) -> str | None:
    """抽取中文之前的英文释义部分。"""
    if not text:
        return None
    match = CJK.search(text)
    english = (text[: match.start()] if match else text).strip()
    english = re.sub(r"\s+", " ", english)
    return english[:400] or None


def parse_pos_tags(text: str) -> list[str]:
    return [POS_MAP[m.group(1).lower()] for m in POS_PATTERN.finditer(text or "")]


def infer_pos(row: SenseRow, meanings: dict[str, str]) -> str:
    """按成员词词性投票推断义项词性；锚词是多义词，放在最后兜底。"""
    votes: Counter[str] = Counter()
    for word in row.members:
        if word.lower() == row.anchor.lower():
            continue
        tags = parse_pos_tags(meanings.get(word.lower(), ""))
        if tags:
            votes[tags[0]] += 1
    if not votes:
        tags = parse_pos_tags(meanings.get(row.anchor.lower(), ""))
        if tags:
            votes[tags[0]] += 1
    if not votes:
        tags = parse_pos_tags(row.gloss)
        if tags:
            votes[tags[0]] += 1
    return votes.most_common(1)[0][0] if votes else "adj"


def effective_actions(decisions: list[dict]) -> dict[str, str]:
    """人工裁决优先；留空视为同意机器建议。返回 word → merge/split。"""
    actions: dict[str, str] = {}
    for item in decisions:
        word = (item.get("word") or "").strip().lower()
        if not word:
            continue
        proposal = (item.get("proposal") or "").strip()
        verdict = (item.get("verdict") or "").strip()
        if verdict in ("合并", "拆分"):
            action = verdict
        else:  # 同意 / 留空：按机器建议执行（含「按机器拆」）
            action = "拆分" if "拆" in proposal else "合并"
        actions[word] = action
    return actions


def pick_main_sense(rows: list[SenseRow], edge_counts: Counter[str]) -> SenseRow:
    """主义项 = 成员最多、其次边最多、最后取 CSV 中靠前的一个。"""

    def order(row: SenseRow) -> tuple[int, int, int]:
        digits = re.sub(r"\D", "", row.code) or "0"
        return (len(row.members), edge_counts[row.code], -int(digits))

    return max(rows, key=order)


def _fit_label(base: str, suffix: str, limit: int = 120) -> str:
    allowed = max(1, limit - len(suffix))
    return (base[:allowed] + suffix)[:limit]


def unique_label(
    base: str,
    pos: str,
    anchor: str,
    members: tuple[str, ...],
    code: str,
    used: dict[tuple[str, str], str],
) -> str:
    """保证 (label_zh, pos) 唯一；冲突时用锚词 / 区分性成员 / 义项 ID 消歧。"""
    key = (base, pos)
    if key not in used:
        used[key] = code
        return base

    distinctive = next(
        (m for m in members if m.lower() != anchor.lower() and m != anchor),
        anchor,
    )
    candidates = [
        _fit_label(base, f"（{anchor}）"),
        _fit_label(base, f"（{distinctive}）"),
        _fit_label(base, f"（{code}）"),
    ]
    for candidate in candidates:
        candidate_key = (candidate, pos)
        if candidate_key not in used:
            used[candidate_key] = code
            return candidate

    index = 2
    while True:
        candidate = _fit_label(base, f"（{code}-{index}）")
        candidate_key = (candidate, pos)
        if candidate_key not in used:
            used[candidate_key] = code
            return candidate
        index += 1


def resolve_book_id(db: Session, book_id: int | None) -> WordBook:
    if book_id is not None:
        book = db.get(WordBook, book_id)
        if book is None:
            raise RuntimeError(f"词书 {book_id} 不存在")
        return book

    active_ids = {
        value
        for value in db.scalars(
            select(AppSetting.active_book_id).where(AppSetting.active_book_id.is_not(None))
        ).all()
        if value
    }
    if not active_ids:
        raise RuntimeError("没有激活词书：先在应用里选择词书，或传 --book-id")
    if len(active_ids) > 1:
        raise RuntimeError(f"有多个账号的激活词书（{sorted(active_ids)}），请用 --book-id 指定")
    book = db.get(WordBook, next(iter(active_ids)))
    if book is None:
        raise RuntimeError("激活词书不存在")
    return book


def word_index(db: Session, book_id: int) -> tuple[dict[str, Word], dict[str, tuple[str, str]]]:
    """拼写（精确 + 小写）→ Word；同时返回拼写 → (释义, 音标)。"""
    words = db.scalars(select(Word).where(Word.book_id == book_id)).all()
    exact = {word.spelling: word for word in words}
    lowered: dict[str, Word] = {}
    for word in words:
        lowered.setdefault(word.spelling.lower(), word)
    return exact, lowered


def existing_graph_size(db: Session, book_id: int) -> int:
    return int(
        db.scalar(select(func.count()).select_from(Sense).where(Sense.book_id == book_id)) or 0
    )


def clear_book_graph(db: Session, book_id: int) -> None:
    """按外键顺序清空一本书的图（义项卡 → 边 → 顶点）。"""
    db.execute(delete(SenseState).where(SenseState.book_id == book_id))
    db.execute(delete(WordSense).where(WordSense.book_id == book_id))
    db.execute(delete(Sense).where(Sense.book_id == book_id))
    db.flush()


def build_graph(
    db: Session,
    book: WordBook,
    senses: list[SenseRow],
    edges: list[EdgeRow],
    decisions: list[dict],
    meanings: dict[str, str],
) -> dict[str, object]:
    exact, lowered = word_index(db, book.id)

    def find_word(spelling: str) -> Word | None:
        return exact.get(spelling) or lowered.get(spelling.lower())

    # 1) 人工裁决 → 每个 review 词的 merge/split，以及合并去向
    actions = effective_actions(decisions)
    edge_counts: Counter[str] = Counter(edge.sense_code for edge in edges)
    by_anchor: dict[str, list[SenseRow]] = defaultdict(list)
    for row in senses:
        by_anchor[row.anchor.lower()].append(row)

    merge_into: dict[str, str] = {}
    for anchor, rows in by_anchor.items():
        if actions.get(anchor) != "合并" or len(rows) < 2:
            continue
        main = pick_main_sense(rows, edge_counts)
        for row in rows:
            if row.code != main.code:
                merge_into[row.code] = main.code

    # 2) 义项星：成员词列 ∪ 边端点（边可能给出成员列之外的词）
    members_by_code: dict[str, set[str]] = {
        row.code: {word for word in row.members} for row in senses
    }
    skipped_words: set[str] = set()
    for edge in edges:
        for spelling in (edge.a, edge.b):
            word = find_word(spelling)
            if word is None:
                skipped_words.add(spelling)
                continue
            members_by_code[edge.sense_code].add(word.spelling)

    # 3) 检查哪些成员在词书里缺失
    for row in senses:
        for spelling in row.members:
            word = find_word(spelling)
            if word is None:
                skipped_words.add(spelling)
            else:
                members_by_code[row.code].add(word.spelling)

    # 4) 建义项（先建全部顶点，再回填 merged_into）
    used_labels: dict[tuple[str, str], str] = {}
    sense_objs: dict[str, Sense] = {}
    # 规范义项先占标签，被合并的旧顶点最后建（避免旧顶点抢走干净 label）
    ordered_senses = sorted(senses, key=lambda row: 1 if row.code in merge_into else 0)
    for row in ordered_senses:
        pos = infer_pos(row, meanings)
        base = chinese_gloss(row.gloss)
        # 词书释义 / 机经释义兜底（避免把英文拼写当选项文本）
        if not base:
            anchor_word = find_word(row.anchor)
            if anchor_word is not None:
                base = chinese_gloss(anchor_word.definition)
        if not base:
            base = chinese_gloss(meanings.get(row.anchor.lower(), ""))
        if not base:
            for member in row.members:
                base = chinese_gloss(meanings.get(member.lower(), ""))
                if base:
                    break
        if not base:
            base = row.anchor

        label = unique_label(base, pos, row.anchor, row.members, row.code, used_labels)
        if merge_into.get(row.code):
            status = MERGED_STATUS
        elif row.source_status == "review" and row.anchor.lower() not in actions:
            status = NEEDS_REVIEW_STATUS
        else:
            status = ACTIVE_STATUS

        sense_objs[row.code] = Sense(
            book_id=book.id,
            label_zh=label,
            definition_en=definition_en(row.gloss),
            pos=pos,
            status=status,
        )
        db.add(sense_objs[row.code])

    db.flush()
    for code, main_code in merge_into.items():
        source = sense_objs.get(code)
        main = sense_objs.get(main_code)
        if source is None or main is None:
            continue
        source.merged_into = main.id
        source.status = MERGED_STATUS

    # 5) 边：合并义项的成员并入主义项；每个 (word, sense) 只写一次
    resolved_members: dict[str, set[str]] = defaultdict(set)
    for row in senses:
        target = merge_into.get(row.code, row.code)
        resolved_members[target].update(members_by_code.get(row.code, set()))

    rows_written = 0
    for code, spellings in resolved_members.items():
        sense = sense_objs.get(code)
        if sense is None or not spellings:
            continue
        edge_status = ACTIVE_STATUS if sense.status == ACTIVE_STATUS else NEEDS_REVIEW_STATUS
        seen: set[int] = set()
        for spelling in sorted(spellings):
            word = find_word(spelling)
            if word is None:
                skipped_words.add(spelling)
                continue
            if word.id in seen:
                continue
            seen.add(word.id)
            db.add(
                WordSense(
                    book_id=book.id,
                    word_id=word.id,
                    sense_id=sense.id,
                    status=edge_status,
                )
            )
            rows_written += 1

    db.flush()

    # 6) 义项卡：只给 active 义项建新卡（due 略早于 now，保证首次 today 就能取到）
    now = utcnow_naive() - timedelta(seconds=1)
    cards = 0
    for code, sense in sense_objs.items():
        if sense.status != ACTIVE_STATUS:
            continue
        if len(resolved_members.get(code, ())) < 2:
            continue
        db.add(SenseState(sense_id=sense.id, book_id=book.id, due=now, status="new"))
        cards += 1

    db.flush()
    return {
        "senses": len(sense_objs),
        "merged_senses": len(merge_into),
        "word_senses": rows_written,
        "sense_states": cards,
        "skipped_words": len(skipped_words),
        "edges": len(edges),
        "skipped": skipped_words,
    }


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    senses_path = args.analysis_dir / "senses.csv"
    edges_path = args.analysis_dir / "sense_edges.csv"
    meanings_path = args.analysis_dir / "jjci_words.json"
    for path in (senses_path, edges_path, meanings_path, args.decisions):
        if not path.exists():
            print(f"[错误] 缺少输入文件：{path}", file=sys.stderr)
            return 1

    senses = read_senses(senses_path)
    edges = read_edges(edges_path)
    decisions_payload = read_json(args.decisions)
    if isinstance(decisions_payload, dict):
        decisions = decisions_payload.get("decisions") or []
    else:
        decisions = decisions_payload
    meanings = {
        (item.get("word") or "").lower(): (item.get("meaning") or "")
        for item in read_json(meanings_path)
        if item.get("word")
    }

    init_db()  # 建库 + 迁移到 v4（幂等）
    book_id: int | None = None
    book_name = ""
    stats: dict[str, object] = {}
    with SessionLocal() as db:
        try:
            book = resolve_book_id(db, args.book_id)
            book_id, book_name = book.id, book.name
            existing = existing_graph_size(db, book.id)
            if existing and not args.force:
                print(
                    f"[跳过] 词书「{book.name}」(id={book.id}) 已有 {existing} 个义项；"
                    "如需重建请加 --force"
                )
                return 0
            if args.dry_run:
                print(
                    f"[dry-run] 词书「{book.name}」(id={book.id})："
                    f"将导入 {len(senses)} 个义项 / {len(edges)} 条边"
                )
                return 0

            if existing and args.force:
                clear_book_graph(db, book.id)

            stats = build_graph(db, book, senses, edges, decisions, meanings)
            db.commit()
        except Exception as exc:  # noqa: BLE001 - 命令行脚本需要给出可读错误
            db.rollback()
            print(f"[错误] 导入失败：{exc}", file=sys.stderr)
            traceback.print_exc()
            return 1

    print(f"词书：{book_name} (id={book_id})")
    print(f"  义项：{stats['senses']}（其中合并 / retired：{stats['merged_senses']}）")
    print(f"  边（word_senses）：{stats['word_senses']}")
    print(f"  义项卡（sense_states）：{stats['sense_states']}")
    print(f"  输入词对：{stats['edges']} 条")
    print(f"  跳过词书外的词：{stats['skipped_words']} 个")
    if stats["skipped_words"]:
        sample = sorted(stats["skipped"])[:15]
        print(f"    样例：{', '.join(sample)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
