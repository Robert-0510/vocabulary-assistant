import uuid

from sqlalchemy import inspect, select, text


def test_migrations_applied(api_client):
    """全新库应包含账号表、FSRS 迁移与多账号列。"""
    from app.database import engine  # 在 api_client 夹具设置临时库之后再解析

    with engine.connect() as conn:
        versions = {r[0] for r in conn.execute(text("SELECT version FROM schema_migrations"))}
        assert {1, 2, 3} <= versions

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"users", "user_sessions", "word_states", "settings"} <= tables

    book_cols = {c["name"] for c in inspector.get_columns("word_books")}
    log_cols = {c["name"] for c in inspector.get_columns("study_logs")}
    state_cols = {c["name"] for c in inspector.get_columns("word_states")}
    setting_cols = {c["name"] for c in inspector.get_columns("settings")}

    assert "user_id" in book_cols
    assert "user_id" in log_cols
    assert "user_id" in setting_cols and "id" not in setting_cols
    assert {"state", "step", "stability", "difficulty", "due", "last_review"} <= state_cols
    assert not {"ease", "interval_days", "due_date", "last_review_at"} & state_cols


def test_migrations_are_idempotent_and_preserve_data(api_client):
    """重复运行迁移不能重放破坏性 DELETE。"""
    from app.database import SessionLocal
    from app.migrations import run_migrations
    from app.models import User

    username = f"sentinel_{uuid.uuid4().hex[:10]}"
    with SessionLocal() as db:
        db.add(User(username=username, password_hash="not-used"))
        db.commit()

    run_migrations()

    with SessionLocal() as db:
        assert db.scalar(select(User.id).where(User.username == username)) is not None
