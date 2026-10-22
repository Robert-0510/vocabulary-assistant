from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services.scheduler import MASTERED_THRESHOLD, apply_answer, derive_status

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


def make_state(**kwargs):
    state = SimpleNamespace(
        state=1,
        step=None,
        stability=None,
        difficulty=None,
        due=None,
        last_review=None,
        reps=0,
        lapses=0,
        status="new",
    )
    for key, value in kwargs.items():
        setattr(state, key, value)
    return state


def test_new_unknown_stays_learning_and_due_soon():
    s = make_state()
    apply_answer(s, "unknown", NOW)
    assert s.state == 1  # Learning
    assert s.status == "learning"
    assert s.stability is not None and s.stability < 1.0
    assert s.lapses == 1 and s.reps == 0
    assert s.due is not None and (s.due - NOW.replace(tzinfo=None)).total_seconds() < 600


def test_new_know_graduates_to_review():
    s = make_state()
    apply_answer(s, "know", NOW)
    assert s.state == 2  # Review
    assert s.status == "reviewing"
    assert 1.0 < s.stability < 5.0
    assert s.reps == 1 and s.lapses == 0
    assert (s.due - NOW.replace(tzinfo=None)).days >= 1


def test_new_master_graduates_with_long_interval():
    s = make_state()
    apply_answer(s, "master", NOW)
    assert s.state == 2
    assert s.stability >= 5.0
    assert (s.due - NOW.replace(tzinfo=None)).days >= 5


def test_learning_correct_graduates():
    s = make_state(
        state=1,
        step=0,
        stability=0.212,
        difficulty=6.4,
        last_review=NOW.replace(tzinfo=None),
        due=NOW.replace(tzinfo=None),
    )
    apply_answer(s, "correct", NOW)
    assert s.state == 2  # Review
    assert s.status == "reviewing"


def test_review_wrong_lapses_to_relearning():
    s = make_state(
        state=2,
        step=None,
        stability=2.3,
        difficulty=2.1,
        last_review=NOW.replace(tzinfo=None),
        due=NOW.replace(tzinfo=None),
        reps=2,
    )
    apply_answer(s, "wrong", NOW)
    assert s.state == 3  # Relearning
    assert s.status == "learning"
    assert s.lapses == 1 and s.reps == 0
    assert s.difficulty > 2.1  # 遗忘后变难


def test_relearning_correct_graduates_back():
    s = make_state(
        state=3,
        step=0,
        stability=0.77,
        difficulty=7.4,
        last_review=NOW.replace(tzinfo=None),
        due=NOW.replace(tzinfo=None),
        lapses=1,
    )
    apply_answer(s, "correct", NOW)
    assert s.state == 2
    assert s.status == "reviewing"


def test_stability_grows_on_consecutive_good():
    s = make_state()
    apply_answer(s, "know", NOW)
    first = s.stability
    later = NOW + timedelta(days=2)
    s2 = make_state(
        state=2,
        step=None,
        stability=first,
        difficulty=s.difficulty,
        last_review=s.last_review,
        due=s.due,
        reps=1,
    )
    apply_answer(s2, "know", later)
    assert s2.stability > first


def test_difficulty_stays_within_bounds():
    s = make_state()
    for _ in range(6):
        apply_answer(s, "wrong", NOW)
        assert 1.0 <= s.difficulty <= 10.0
        # 保持未毕业状态反复遗忘
        s = make_state(
            state=s.state,
            step=s.step,
            stability=s.stability,
            difficulty=s.difficulty,
            last_review=s.last_review,
            due=s.due,
            lapses=s.lapses,
            reps=0,
            status=s.status,
        )


def test_derive_status():
    assert derive_status(1, None) == "new"
    assert derive_status(1, 0.5) == "learning"
    assert derive_status(3, 2.0) == "learning"
    assert derive_status(2, 10.0) == "reviewing"
    assert derive_status(2, MASTERED_THRESHOLD) == "mastered"
    assert derive_status(2, 200.0) == "mastered"
