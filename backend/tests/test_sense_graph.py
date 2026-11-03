"""P1 接口层：义项拆解 / 多选释义 / 等价组 / 代表词 FSRS。"""

from sqlalchemy import select

BOOK = """# 义项测试词书

| 单词 | 音标 | 释义 | 例句 |
|---|---|---|---|
| manifest | /ˈmænɪfest/ | adj. 明显的 v. 显示 | His relief was manifest. |
| evident | /ˈevɪdənt/ | adj. 明显的 | |
| obvious | /ˈɒbviəs/ | adj. 明显的 | |
| patent | /ˈpeɪtnt/ | adj. 明显的 | |
| self-evident | /ˌself ˈevɪdənt/ | adj. 不证自明的 | |
| reveal | /rɪˈviːl/ | v. 显示 | |
| abandon | /əˈbændən/ | v. 放弃 | |
| benefit | /ˈbenɪfɪt/ | n. 好处 | |
| crucial | /ˈkruːʃl/ | adj. 至关重要的 | |
| emerge | /ɪˈmɜːdʒ/ | v. 出现 | |
"""


def upload_book(client) -> int:
    resp = client.post(
        "/api/books/upload",
        files={"file": ("sense.md", BOOK.encode("utf-8"), "text/markdown")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["book_id"]


def word_id(book_id: int, spelling: str) -> int:
    from app.database import SessionLocal
    from app.models import Word

    with SessionLocal() as db:
        return db.scalar(select(Word.id).where(Word.book_id == book_id, Word.spelling == spelling))


def senses_of(word_id_: int) -> dict[int, str]:
    from app.database import SessionLocal
    from app.models import Sense, WordSense

    with SessionLocal() as db:
        rows = db.execute(
            select(Sense.id, Sense.label_zh)
            .join(WordSense, WordSense.sense_id == Sense.id)
            .where(WordSense.word_id == word_id_)
        ).all()
        return {sense_id: label for sense_id, label in rows}


def sense_members(sense_id: int) -> set[int]:
    from app.database import SessionLocal
    from app.models import WordSense

    with SessionLocal() as db:
        return set(
            db.scalars(select(WordSense.word_id).where(WordSense.sense_id == sense_id)).all()
        )


def curate(book_id: int) -> None:
    """把上传书拆出来的义项标成精选，模拟「审核过的等价词图」。"""
    from app.database import SessionLocal
    from app.models import Sense
    from sqlalchemy import update

    with SessionLocal() as db:
        db.execute(update(Sense).where(Sense.book_id == book_id).values(is_curated=True))
        db.commit()


def today(client):
    resp = client.get("/api/study/today")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_upload_decomposes_senses_and_shares_labels(auth_client):
    book_id = upload_book(auth_client)

    manifest = senses_of(word_id(book_id, "manifest"))
    assert set(manifest.values()) == {"明显的", "显示"}, "多义词按词性拆成两个义项"

    evident = senses_of(word_id(book_id, "evident"))
    assert list(evident.values()) == ["明显的"]

    # 「明显的」是共享义项：manifest/evident/obvious/patent 同一条
    shared_id = next(iter(evident))
    assert sense_members(shared_id) == {
        word_id(book_id, name) for name in ("manifest", "evident", "obvious", "patent")
    }


def test_single_sense_word_gets_four_option_meaning_quiz(auth_client):
    book_id = upload_book(auth_client)
    body = today(auth_client)

    item = next(word for word in body["new_words"] if word["spelling"] == "abandon")
    quiz = item["quiz"]
    assert quiz["type"] == "meaning_multi"
    assert quiz["option_count"] == 4 == len(quiz["options"])
    correct = set(senses_of(word_id(book_id, "abandon")))
    assert correct <= {option["id"] for option in quiz["options"]}
    assert "answer_index" not in quiz


def test_polysemous_word_gets_correct_plus_two_options(auth_client):
    book_id = upload_book(auth_client)
    body = today(auth_client)

    item = next(word for word in body["new_words"] if word["spelling"] == "manifest")
    quiz = item["quiz"]
    correct = set(senses_of(word_id(book_id, "manifest")))
    assert quiz["type"] == "meaning_multi"
    assert len(correct) == 2
    assert quiz["option_count"] == max(5, len(correct) + 2) == len(quiz["options"])
    assert correct <= {option["id"] for option in quiz["options"]}


def test_partial_answer_maps_to_hard_without_resetting_reps(auth_client):
    book_id = upload_book(auth_client)
    target = word_id(book_id, "manifest")  # 多义词，非代表词 → 词题计分
    correct = sorted(senses_of(target))

    first = auth_client.post(
        "/api/study/answer",
        json={"kind": "word", "target_id": target, "phase": "meaning", "selected_ids": correct},
    )
    assert first.status_code == 200, first.text
    assert first.json()["result"] == "correct"

    from app.database import SessionLocal
    from app.models import WordState

    with SessionLocal() as db:
        state = db.scalar(select(WordState).where(WordState.word_id == target))
        assert state.reps == 1
        difficulty_after_good = float(state.difficulty)

    second = auth_client.post(
        "/api/study/answer",
        json={
            "kind": "word",
            "target_id": target,
            "phase": "meaning",
            "selected_ids": [correct[0]],
        },
    )
    assert second.status_code == 200, second.text
    payload = second.json()
    assert payload["result"] == "partial"
    assert payload["selected_correct"] == 1
    assert payload["correct_total"] == 2

    with SessionLocal() as db:
        state = db.scalar(select(WordState).where(WordState.word_id == target))
        assert state.reps == 2
        assert state.lapses == 0
        assert float(state.difficulty) > difficulty_after_good


def test_representative_meaning_answer_is_warmup(auth_client):
    """代表词的词题只热身：不写 FSRS，等等价组题记分。"""
    book_id = upload_book(auth_client)
    curate(book_id)
    target = word_id(book_id, "evident")  # 组内义项最少 → 代表词
    correct = sorted(senses_of(target))

    resp = auth_client.post(
        "/api/study/answer",
        json={"kind": "word", "target_id": target, "phase": "meaning", "selected_ids": correct},
    )
    assert resp.status_code == 200, resp.text

    from app.database import SessionLocal
    from app.models import StudyLog, WordState

    with SessionLocal() as db:
        state = db.scalar(select(WordState).where(WordState.word_id == target))
        assert state.stability is None, "代表词的词题不排期"
        logs = db.scalars(select(StudyLog).where(StudyLog.word_id == target)).all()
        assert logs, "热身题仍然记日志"


def test_equiv_group_quiz_and_distractors(auth_client):
    book_id = upload_book(auth_client)
    curate(book_id)
    body = today(auth_client)

    assert body["sense_items"], "代表词应生成等价组题"
    for item in body["sense_items"]:
        quiz = item["quiz"]
        assert quiz["type"] == "equiv_group"
        assert quiz["owner_word_id"] == word_id(book_id, quiz["question"])
        members = sense_members(item["id"])
        anchor = quiz["owner_word_id"]
        correct = members - {anchor}
        option_ids = {option["id"] for option in quiz["options"]}
        assert correct <= option_ids
        for option in quiz["options"]:
            if option["id"] not in correct:
                assert option["id"] not in members, "干扰项不能来自同一义项"


def test_sense_answer_updates_representative_word_state_not_sense_state(auth_client):
    book_id = upload_book(auth_client)
    curate(book_id)
    body = today(auth_client)
    item = next(entry for entry in body["sense_items"] if len(sense_members(entry["id"])) >= 4)
    quiz = item["quiz"]
    anchor = quiz["owner_word_id"]
    correct = sorted(sense_members(item["id"]) - {anchor})

    from app.database import SessionLocal
    from app.models import WordState

    with SessionLocal() as db:
        before = {
            state.word_id: (state.status, state.stability, state.reps, state.due)
            for state in db.scalars(select(WordState)).all()
        }

    resp = auth_client.post(
        "/api/study/answer",
        json={"kind": "sense", "target_id": item["id"], "phase": "group", "selected_ids": correct},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["result"] == "correct"

    with SessionLocal() as db:
        after = {
            state.word_id: (state.status, state.stability, state.reps, state.due)
            for state in db.scalars(select(WordState)).all()
        }
        changed = {word for word in after if after[word] != before[word]}
        assert changed == {anchor}, "只更新代表词的词卡，选项词不变"
        assert db.scalar(select(WordState).where(WordState.word_id == anchor)).reps == 1


def test_today_response_never_leaks_answer_sets(auth_client):
    book_id = upload_book(auth_client)
    curate(book_id)
    body = today(auth_client)

    quizzes = [
        word["quiz"]
        for word in body["new_words"] + body["review_words"] + body["sense_items"]
        if word["quiz"]
    ]
    assert any(quiz["type"] == "meaning_multi" for quiz in quizzes)
    assert any(quiz["type"] == "equiv_group" for quiz in quizzes)
    allowed = {"type", "question", "options", "option_count", "owner_word_id"}
    for quiz in quizzes:
        assert "answer_index" not in quiz
        assert set(quiz) <= allowed
        for option in quiz["options"]:
            assert set(option) == {"id", "text"}
