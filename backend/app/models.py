"""数据库模型：词书 / 单词 / 学习状态 / 学习流水 / 设置。"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

STATUS_VALUES = ("new", "learning", "reviewing", "mastered")
PHASE_VALUES = ("new_first", "new_quiz", "review", "relearn", "meaning", "group")
RESULT_VALUES = ("know", "unknown", "master", "correct", "wrong", "partial")


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"mysql_charset": "utf8mb4"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        Index("ix_sessions_user", "user_id"),
        Index("ix_sessions_expires", "expires_at"),
        {"mysql_charset": "utf8mb4"},
    )

    # 只存 token 的 SHA-256，cookie 中的原始 token 不落库
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class WordBook(Base):
    __tablename__ = "word_books"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_books_user_name"),
        Index("ix_books_user", "user_id"),
        {"mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    words: Mapped[list["Word"]] = relationship(
        back_populates="book", cascade="all, delete-orphan", passive_deletes=True
    )


class Word(Base):
    __tablename__ = "words"
    __table_args__ = (
        UniqueConstraint("book_id", "spelling", name="uq_words_book_spelling"),
        Index("ix_words_book_seq", "book_id", "seq"),
        {"mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("word_books.id", ondelete="CASCADE"), nullable=False
    )
    spelling: Mapped[str] = mapped_column(String(100), nullable=False)
    phonetic: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    definition: Mapped[str] = mapped_column(String(1000), nullable=False)
    example_en: Mapped[str | None] = mapped_column(Text)
    example_cn: Mapped[str | None] = mapped_column(String(500))
    seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    book: Mapped[WordBook] = relationship(back_populates="words")
    state: Mapped["WordState | None"] = relationship(
        back_populates="word",
        cascade="all, delete-orphan",
        uselist=False,
        passive_deletes=True,
    )


class WordState(Base):
    __tablename__ = "word_states"
    __table_args__ = (
        Index("ix_states_book_status", "book_id", "status"),
        Index("ix_states_due", "due"),
        Index("ix_states_stability", "stability"),
        {"mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    word_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("words.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    book_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("word_books.id", ondelete="CASCADE"), nullable=False
    )
    # FSRS 状态：1=Learning 2=Review 3=Relearning；stability 为 NULL 表示尚未学习的新词
    state: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    step: Mapped[int | None] = mapped_column(SmallInteger)
    stability: Mapped[float | None] = mapped_column(Numeric(12, 4))
    difficulty: Mapped[float | None] = mapped_column(Numeric(12, 4))
    reps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lapses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    due: Mapped[datetime | None] = mapped_column(DateTime)
    last_review: Mapped[datetime | None] = mapped_column(DateTime)
    # 派生的 UI 状态（new/learning/reviewing/mastered），由调度器每次更新时写入
    status: Mapped[str] = mapped_column(
        Enum(*STATUS_VALUES, name="word_status_enum"), default="new", nullable=False
    )

    word: Mapped[Word] = relationship(back_populates="state")


class StudyLog(Base):
    __tablename__ = "study_logs"
    __table_args__ = (
        Index("ix_logs_studied_at", "studied_at"),
        Index("ix_logs_user_studied", "user_id", "studied_at"),
        Index("ix_logs_word", "word_id"),
        {"mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    word_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("words.id", ondelete="CASCADE"), nullable=False
    )
    phase: Mapped[str] = mapped_column(Enum(*PHASE_VALUES, name="phase_enum"), nullable=False)
    result: Mapped[str] = mapped_column(Enum(*RESULT_VALUES, name="result_enum"), nullable=False)
    studied_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SchemaMigration(Base):
    """已应用的数据库迁移版本，防止升级时重复执行 DDL。"""

    __tablename__ = "schema_migrations"
    __table_args__ = {"mysql_charset": "utf8mb4"}

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    description: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AppSetting(Base):
    __tablename__ = "settings"
    __table_args__ = {"mysql_charset": "utf8mb4"}

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    new_per_day: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    review_per_day: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    active_book_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("word_books.id", ondelete="SET NULL")
    )


class Sense(Base):
    """义项顶点（二部图右侧）。

    label_zh 是规范名（短中文义项），不同措辞放 word_senses.gloss_raw；
    合并只留痕：旧顶点 status='retired' + merged_into 指向规范义项。
    """

    __tablename__ = "senses"
    __table_args__ = (
        UniqueConstraint("book_id", "label_zh", "pos", name="uq_sense_book_label_pos"),
        Index("ix_sense_book_status", "book_id", "status"),
        {"mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("word_books.id", ondelete="CASCADE"), nullable=False
    )
    label_zh: Mapped[str] = mapped_column(String(120), nullable=False)
    definition_en: Mapped[str | None] = mapped_column(String(400))
    pos: Mapped[str] = mapped_column(String(16), nullable=False, default="adj")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="needs_review")
    merged_into: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class WordSense(Base):
    """词—义项关联（二部图的边）。"""

    __tablename__ = "word_senses"
    __table_args__ = (
        UniqueConstraint("word_id", "sense_id", name="uq_word_sense"),
        Index("ix_ws_sense_status", "sense_id", "status"),
        Index("ix_ws_word_status", "word_id", "status"),
        {"mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    word_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("words.id", ondelete="CASCADE"), nullable=False
    )
    sense_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("senses.id", ondelete="CASCADE"), nullable=False
    )
    gloss_raw: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")


class SenseState(Base):
    """义项卡（FSRS），字段与 word_states 完全一致。"""

    __tablename__ = "sense_states"
    __table_args__ = (
        Index("ix_sense_states_due", "due"),
        {"mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sense_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("senses.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    book_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    step: Mapped[int | None] = mapped_column(SmallInteger)
    stability: Mapped[float | None] = mapped_column(Numeric(12, 4))
    difficulty: Mapped[float | None] = mapped_column(Numeric(12, 4))
    reps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lapses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    due: Mapped[datetime | None] = mapped_column(DateTime)
    last_review: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default="new", nullable=False)
