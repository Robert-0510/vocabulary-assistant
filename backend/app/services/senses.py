"""上传词书的义项拆解：把一条释义切成 1..n 个义项。

规则（与离线管线一致的口径）：
- 用词性标记（`adj.` / `n.` / `v.` / `adv.` …）作为义项边界；
- 同一次出现的「；」只分隔同义表达，不拆义项；
- 没有词性标记时整条释义算一个义项。

这样「v. 放弃；抛弃」是 1 个义项，「adj. 学术的 n. 学者」是 2 个义项。
"""

from __future__ import annotations

import re

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Sense, Word, WordSense

POS_TAG = re.compile(r"(?<![A-Za-z])(adj|adv|n|v|vt|vi|prep|conj|pron|num)\.", re.I)
POS_MAP = {"vt": "v", "vi": "v"}
MAX_LABEL = 120
MAX_SENSES_PER_WORD = 6  # 选项数 = 义项数 + 2，超过 6 会超出 1–9 键的范围


def split_senses(definition: str) -> list[tuple[str, str]]:
    """把一条释义拆成 [(词性, 中文释义), ...]；空释义返回空列表。"""
    text = (definition or "").strip()
    if not text:
        return []
    marks = list(POS_TAG.finditer(text))
    if not marks:
        return [("", text[:MAX_LABEL])]

    parts: list[tuple[str, str]] = []
    for i, mark in enumerate(marks):
        start = mark.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        gloss = text[start:end].strip(" 　；;，,、·-")
        if not gloss:
            continue
        pos = POS_MAP.get(mark.group(1).lower(), mark.group(1).lower())
        parts.append((pos, gloss[:MAX_LABEL]))

    if not parts:
        return [("", text[:MAX_LABEL])]
    if len(parts) > MAX_SENSES_PER_WORD:  # 合并超出上限的义项，避免选项超过 9 个
        head = parts[: MAX_SENSES_PER_WORD - 1]
        rest = "；".join(gloss for _, gloss in parts[MAX_SENSES_PER_WORD - 1 :])
        head.append((parts[MAX_SENSES_PER_WORD - 1][0], rest[:MAX_LABEL]))
        parts = head
    return parts


def rebuild_word_senses(db: Session, book_id: int, word: Word) -> int:
    """按当前 definition 重建某个词的义项（只删除仅属于该词的义项）。

    同一本书里释义与词性都相同的义项会被复用，这样「明显的」这种共同释义
    能自然形成等价组，而不是每个词各建一条。
    """
    old_ids = db.scalars(select(WordSense.sense_id).where(WordSense.word_id == word.id)).all()
    for sense_id in old_ids:
        shared = db.scalar(
            select(func.count())
            .select_from(WordSense)
            .where(WordSense.sense_id == sense_id, WordSense.word_id != word.id)
        )
        if not shared:
            db.execute(delete(WordSense).where(WordSense.sense_id == sense_id))
            db.execute(delete(Sense).where(Sense.id == sense_id))

    count = 0
    for pos, label in split_senses(word.definition):
        pos = (pos or "phrase")[:16]
        sense = db.scalar(
            select(Sense).where(
                Sense.book_id == book_id,
                Sense.label_zh == label,
                Sense.pos == pos,
                Sense.status == "active",
            )
        )
        if sense is None:
            sense = Sense(book_id=book_id, label_zh=label, pos=pos, status="active")
            db.add(sense)
            db.flush()
        db.add(WordSense(book_id=book_id, word_id=word.id, sense_id=sense.id, status="active"))
        count += 1
    return count
