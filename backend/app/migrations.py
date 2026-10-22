"""轻量级、可版本化的数据库迁移。

规则：
- 每次结构变更在 MIGRATIONS 末尾追加一个 Migration，**不要修改已发布的迁移**；
- 启动时自动执行尚未应用的迁移，并记录到 schema_migrations 表；
- 旧的、由 create_all 直接建表的数据库会在首次运行时被标记为基线版本。
"""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Connection

from app.database import Base, engine
from app.models import AppSetting, SchemaMigration

BASELINE_VERSION = 1


@dataclass(frozen=True)
class Migration:
    version: int
    description: str
    apply: Callable[[Connection], None]


def _fsrs_schema_migration(conn: Connection) -> None:
    """清空旧数据并把 word_states 从 SM-2 列切换为 FSRS 列（幂等）。"""
    # 1) 清空（落实「删除示例词书、不迁移旧进度」；外键级联亦会清空，这里显式按序删除）
    for table in ("study_logs", "word_states", "words", "word_books"):
        conn.execute(text(f"DELETE FROM `{table}`"))
    conn.execute(text("UPDATE settings SET active_book_id = NULL"))

    # 2) 列交换：旧列存在则删，新列缺失则加
    inspector = inspect(conn)
    cols = {c["name"] for c in inspector.get_columns("word_states")}
    for old in ("ease", "interval_days", "due_date", "last_review_at"):
        if old in cols:
            conn.execute(text(f"ALTER TABLE word_states DROP COLUMN `{old}`"))

    new_columns = {
        "state": "SMALLINT NOT NULL DEFAULT 1",
        "step": "SMALLINT NULL",
        "stability": "DECIMAL(12,4) NULL",
        "difficulty": "DECIMAL(12,4) NULL",
        "due": "DATETIME NULL",
        "last_review": "DATETIME NULL",
    }
    for name, ddl in new_columns.items():
        if name not in cols:
            conn.execute(text(f"ALTER TABLE word_states ADD COLUMN `{name}` {ddl}"))

    # 3) due 索引（原 ix_states_due 建在 due_date 上，随列删除被 MySQL 自动移除）
    inspector = inspect(conn)
    indexes = {i["name"] for i in inspector.get_indexes("word_states")}
    if "ix_states_due" not in indexes:
        conn.execute(text("ALTER TABLE word_states ADD INDEX `ix_states_due` (`due`)"))


def _has_fk_column(conn: Connection, table: str, column: str) -> bool:
    return any(column in fk["constrained_columns"] for fk in inspect(conn).get_foreign_keys(table))


def _accounts_migration(conn: Connection) -> None:
    """引入多账号：清空无归属的旧数据，并给业务表补 user_id / 重建 settings。"""
    # 1) 硬删除账号体系之前的无主数据（当前库为空；不做软删除）
    for table in ("study_logs", "word_states", "words", "word_books"):
        conn.execute(text(f"DELETE FROM `{table}`"))

    # 2) settings：旧的单行配置表 → 每账号一行
    settings_cols = {c["name"] for c in inspect(conn).get_columns("settings")}
    if "user_id" not in settings_cols:
        conn.execute(text("DROP TABLE settings"))
        AppSetting.__table__.create(bind=conn, checkfirst=True)

    # 3) word_books：归属账号 + 账号内唯一书名
    book_cols = {c["name"] for c in inspect(conn).get_columns("word_books")}
    if "user_id" not in book_cols:
        conn.execute(text("ALTER TABLE word_books ADD COLUMN user_id BIGINT NULL"))
    conn.execute(text("ALTER TABLE word_books MODIFY user_id BIGINT NOT NULL"))

    book_indexes = {i["name"] for i in inspect(conn).get_indexes("word_books")}
    if "name" in book_indexes:
        conn.execute(text("ALTER TABLE word_books DROP INDEX `name`"))
    if "ix_books_user" not in book_indexes:
        conn.execute(text("ALTER TABLE word_books ADD INDEX ix_books_user (user_id)"))
    if "uq_books_user_name" not in book_indexes:
        conn.execute(
            text("ALTER TABLE word_books ADD UNIQUE KEY uq_books_user_name (user_id, name)")
        )
    if not _has_fk_column(conn, "word_books", "user_id"):
        conn.execute(
            text(
                "ALTER TABLE word_books ADD CONSTRAINT fk_books_user "
                "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE"
            )
        )

    # 4) study_logs：归属账号，便于统计直接按账号过滤
    log_cols = {c["name"] for c in inspect(conn).get_columns("study_logs")}
    if "user_id" not in log_cols:
        conn.execute(text("ALTER TABLE study_logs ADD COLUMN user_id BIGINT NULL"))
    conn.execute(text("ALTER TABLE study_logs MODIFY user_id BIGINT NOT NULL"))

    log_indexes = {i["name"] for i in inspect(conn).get_indexes("study_logs")}
    if "ix_logs_user_studied" not in log_indexes:
        conn.execute(
            text("ALTER TABLE study_logs ADD INDEX ix_logs_user_studied (user_id, studied_at)")
        )
    if not _has_fk_column(conn, "study_logs", "user_id"):
        conn.execute(
            text(
                "ALTER TABLE study_logs ADD CONSTRAINT fk_logs_user "
                "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE"
            )
        )


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        2,
        "replace SM-2 scheduler with FSRS (drop ease/interval, add stability/difficulty)",
        _fsrs_schema_migration,
    ),
    Migration(3, "add multi-account users and per-user data ownership", _accounts_migration),
)


CURRENT_SCHEMA_VERSION = MIGRATIONS[-1].version if MIGRATIONS else BASELINE_VERSION


def run_migrations() -> None:
    """create_all 补建缺失的表，然后执行未应用的版本化迁移。

    全新数据库：create_all 已经按当前模型建好表，直接把基线及历史迁移标记为已应用，
    避免执行开发期迁移中的 DELETE FROM 清空逻辑。
    已有数据库：保留原有升级路径（旧库仍按序执行 2/3）。
    """
    existing_tables = set(inspect(engine).get_table_names())
    fresh_database = not ({"word_books", "users", "schema_migrations"} & existing_tables)

    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        applied = set(conn.execute(select(SchemaMigration.version)).scalars().all())
        if not applied and fresh_database:
            rows = [
                {"version": BASELINE_VERSION, "description": "baseline (fresh install)"},
                *[{"version": m.version, "description": m.description[:200]} for m in MIGRATIONS],
            ]
            conn.execute(SchemaMigration.__table__.insert(), rows)
            return

        if not applied:
            # 旧库没有迁移记录：当前结构即基线，直接盖章，不重复建表
            conn.execute(
                SchemaMigration.__table__.insert().values(
                    version=BASELINE_VERSION, description="baseline"
                )
            )
            applied.add(BASELINE_VERSION)

        for migration in MIGRATIONS:
            if migration.version in applied:
                continue
            migration.apply(conn)
            conn.execute(
                SchemaMigration.__table__.insert().values(
                    version=migration.version,
                    description=migration.description[:200],
                )
            )
