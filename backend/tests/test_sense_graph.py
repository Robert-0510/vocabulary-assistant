"""P1 接口层：多选释义 / 等价组 / 义项卡调度与判分。"""

from datetime import timedelta

from sqlalchemy import select

BOOK = """# 义项测试词书

| 单词 | 音标 | 释义 | 例句 |
|---|---|---|---|
| manifest | /ˈmænɪfest/ | adj. 明显的 v. 显示 | His relief was manifest. 他的宽慰显而易见。 |
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

# (label, pos, members, has_sense_card)
SENSE_LAYOUT = [
    ("明显的", "adj", ["manifest", "evident", "obvious", "patent", "self-evident"], True),
    ("显示", "v", ["manifest", "reveal"], True),
    ("放弃", "v", ["abandon"], False),
    ("好处", "n", ["benefit"], False),
    ("至关重要的", "adj", ["crucial"], False),
    ("出现", "v", ["emerge"], False),
]


def upload_book(client) -> int:
    resp = client.post(
        "/api/books/upload",
        files={"file": ("sense.md", BOOK.encode("utf-8"), "text/markdown")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["book_id"]


def seed_graph(book_id: int) -> dict[str, int]:
    """写入义项图并给两条义项建到期卡；返回 label → sense_id。"""
    from app.database import SessionLocal
    from app.models import Sense, SenseState, Word, WordSense
    from app.services.scheduler import utcnow_naive

    with SessionLocal() as db:
        word_ids = {
            word.spelling: word.id
            for word in db.scalars(select(Word).where(Word.book_id == book_id)).all()
        }
        sense_ids: dict[str, int] = {}
        for label, pos, members, has_card in SENSE_LAYOUT:
            sense = Sense(book_id=book_id, label_zh=label, pos=pos, status="active")
            db.add(sense)
            db.flush()
            sense_ids[label] = sense.id
            for spelling in members:
                db.add(
                    WordSense(
                        book_id=book_id,
                        word_id=word_ids[spelling],
                        sense_id=sense.id,
                        status="active",
                    )
                )
            if has_card:
                db.add(
                    SenseState(
                        sense_id=sense.id,
                        book_id=book_id,
                        due=utcnow_naive() - timedelta(seconds=1),
                        status="new",
                    )
                )
        db.commit()
    return sense_ids


def word_id(book_id: int, spelling: str) -> int:
    from app.database import SessionLocal
    from app.models import Word

    with SessionLocal() as db:
        return db.scalar(select(Word.id).where(Word.book_id == book_id, Word.spelling == spelling))


def sense_members(sense_id: int) -> set[int]:
    from app.database import SessionLocal
    from app.models import WordSense

    with SessionLocal() as db:
        return {
            row
            for row in db.scalars(
                select(WordSense.word_id).where(WordSense.sense_id == sense_id)
            ).all()
        }


def today(client):
    resp = client.get("/api/study/today")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_single_sense_word_gets_four_option_meaning_quiz(auth_client):
    book_id = upload_book(auth_client)
    senses = seed_graph(book_id)
    body = today(auth_client)

    item = next(word for word in body["new_words"] if word["spelling"] == "abandon")
    quiz = item["quiz"]
    assert quiz["type"] == "meaning_multi"
    assert quiz["option_count"] == 4 == len(quiz["options"])
    assert senses["放弃"] in {option["id"] for option in quiz["options"]}
    assert "answer_index" not in quiz


def test_polysemous_word_gets_more_options(auth_client):
    book_id = upload_book(auth_client)
    senses = seed_graph(book_id)
    body = today(auth_client)

    item = next(word for word in body["new_words"] if word["spelling"] == "manifest")
    quiz = item["quiz"]
    correct = {senses["明显的"], senses["显示"]}
    assert quiz["type"] == "meaning_multi"
    assert len(quiz["options"]) == max(5, len(correct) + 2)
    assert quiz["option_count"] == len(quiz["options"])
    assert correct <= {option["id"] for option in quiz["options"]}


def test_partial_answer_maps_to_hard_without_resetting_reps(auth_client):
    book_id = upload_book(auth_client)
    senses = seed_graph(book_id)
    target = word_id(book_id, "manifest")
    correct = [senses["明显的"], senses["显示"]]

    first = auth_client.post(
        "/api/study/answer",
        json={
            "kind": "word",
            "target_id": target,
            "phase": "meaning",
            "selected_ids": correct,
        },
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
        assert state.reps == 2  # Hard 不重置 reps
        assert state.lapses == 0
        assert float(state.difficulty) > difficulty_after_good  # 部分正确提高难度
        assert state.status in ("reviewing", "learning")


def test_equiv_group_distractors_are_outside_the_sense(auth_client):
    book_id = upload_book(auth_client)
    seed_graph(book_id)
    body = today(auth_client)

    assert body["sense_items"], "到期义项卡应生成 equiv_group"
    for item in body["sense_items"]:
        quiz = item["quiz"]
        assert quiz["type"] == "equiv_group"
        members = sense_members(item["id"])
        anchor = word_id(book_id, quiz["question"])
        correct = members - {anchor}
        option_ids = {option["id"] for option in quiz["options"]}
        assert correct <= option_ids
        for option in quiz["options"]:
            if option["id"] not in correct:
                assert option["id"] not in members, f"干扰项 {option['text']} 与正确答案同义项"


def test_sense_answer_only_updates_sense_state(auth_client):
    book_id = upload_book(auth_client)
    seed_graph(book_id)
    body = today(auth_client)
    item = next(
        entry for entry in body["sense_items"] if entry["spelling"] != "reveal"
    )  # 取成员较多的「明显的」星
    quiz = item["quiz"]
    members = sense_members(item["id"])
    anchor = word_id(book_id, quiz["question"])
    correct = sorted(members - {anchor})
    assert len(correct) >= 2

    from app.database import SessionLocal
    from app.models import SenseState, WordState

    with SessionLocal() as db:
        before = {
            state.word_id: (
                state.status,
                state.stability,
                state.difficulty,
                state.reps,
                state.lapses,
                state.due,
                state.last_review,
            )
            for state in db.scalars(select(WordState).where(WordState.book_id == book_id)).all()
        }

    resp = auth_client.post(
        "/api/study/answer",
        json={
            "kind": "sense",
            "target_id": item["id"],
            "phase": "group",
            "selected_ids": correct,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["result"] == "correct"

    with SessionLocal() as db:
        sense_state = db.scalar(select(SenseState).where(SenseState.sense_id == item["id"]))
        assert sense_state.reps == 1
        assert sense_state.stability is not None
        after = {
            state.word_id: (
                state.status,
                state.stability,
                state.difficulty,
                state.reps,
                state.lapses,
                state.due,
                state.last_review,
            )
            for state in db.scalars(select(WordState).where(WordState.book_id == book_id)).all()
        }
    assert before == after, "义项作答不得改写任何 word_states"


def test_today_response_never_leaks_answer_sets(auth_client):
    book_id = upload_book(auth_client)
    seed_graph(book_id)
    body = today(auth_client)

    quizzes = [
        word["quiz"]
        for word in body["new_words"] + body["review_words"] + body["sense_items"]
        if word["quiz"]
    ]
    assert any(quiz["type"] == "meaning_multi" for quiz in quizzes)
    assert any(quiz["type"] == "equiv_group" for quiz in quizzes)
    for quiz in quizzes:
        if quiz["type"] not in ("meaning_multi", "equiv_group"):
            continue
        assert "answer_index" not in quiz
        assert set(quiz) <= {"type", "question", "options", "option_count"}
        for option in quiz["options"]:
            assert set(option) == {"id", "text"}
