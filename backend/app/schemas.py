"""Pydantic 请求/响应模型。"""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------- 账号 ----------


class UserOut(BaseModel):
    id: int
    username: str


class AuthIn(BaseModel):
    username: str
    password: str


class DeleteAccountIn(BaseModel):
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


# ---------- 词书 ----------


class UploadResult(BaseModel):
    book_id: int
    name: str
    imported: int
    skipped: int


class BookCounts(BaseModel):
    new: int = 0
    learning: int = 0
    reviewing: int = 0
    mastered: int = 0


class BookOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    word_count: int
    created_at: datetime
    is_active: bool
    counts: BookCounts


class WordOut(BaseModel):
    id: int
    spelling: str
    phonetic: str
    definition: str
    example_en: str | None = None
    example_cn: str | None = None
    seq: int
    status: str
    interval_days: float
    stability: float | None = None
    difficulty: float | None = None
    reps: int
    lapses: int
    due_date: date | None = None


class WordPage(BaseModel):
    total: int
    items: list[WordOut]


class WordUpdateIn(BaseModel):
    """词表纠错：只更新显式传入的字段。"""

    model_config = ConfigDict(extra="ignore")

    spelling: str | None = Field(default=None, max_length=100)
    phonetic: str | None = Field(default=None, max_length=200)
    definition: str | None = Field(default=None, max_length=1000)
    example_en: str | None = Field(default=None, max_length=2000)
    example_cn: str | None = Field(default=None, max_length=500)


# ---------- 备份 / 导入 ----------


class BackupWordState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    state: int = 1
    step: int | None = None
    stability: float | None = None
    difficulty: float | None = None
    due: datetime | None = None
    last_review: datetime | None = None
    reps: int = 0
    lapses: int = 0
    status: str = "new"


class BackupLog(BaseModel):
    model_config = ConfigDict(extra="ignore")

    phase: str
    result: str
    studied_at: datetime | None = None


class BackupWord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    spelling: str = Field(min_length=1, max_length=100)
    phonetic: str = Field(default="", max_length=200)
    definition: str = Field(min_length=1, max_length=1000)
    example_en: str | None = Field(default=None, max_length=2000)
    example_cn: str | None = Field(default=None, max_length=500)
    seq: int = 0
    state: BackupWordState | None = None
    logs: list[BackupLog] = Field(default_factory=list)


class BackupBook(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    words: list[BackupWord] = Field(default_factory=list)


class BackupSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    new_per_day: int = Field(default=25, ge=5, le=300)
    review_per_day: int = Field(default=50, ge=10, le=600)


class BackupPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    format: str
    version: int = 1
    app_version: str | None = None
    exported_at: datetime | None = None
    settings: BackupSettings | None = None
    active_book_name: str | None = None
    books: list[BackupBook] = Field(default_factory=list)


class ImportResult(BaseModel):
    books_imported: int
    words_imported: int
    skipped: int


# ---------- 学习 ----------


class QuizOptionOut(BaseModel):
    id: int
    text: str


class LegacyQuizOut(BaseModel):
    """旧题型（兜底）：词书没有义项数据时继续使用，前端本地判分。"""

    type: Literal["en2cn", "cn2en", "cloze"]
    question: str
    options: list[str]
    answer_index: int


class MultiQuizOut(BaseModel):
    """新题型：多选释义 / 等价组。服务端判分，响应不含正确集合。"""

    type: Literal["meaning_multi", "equiv_group"]
    question: str
    options: list[QuizOptionOut]
    option_count: int


QuizOut = Annotated[LegacyQuizOut | MultiQuizOut, Field(discriminator="type")]


class StudyWordOut(BaseModel):
    id: int
    spelling: str
    phonetic: str
    definition: str
    example_en: str | None = None
    example_cn: str | None = None
    status: str
    quiz: QuizOut | None = None


class TodayOut(BaseModel):
    new_words: list[StudyWordOut]
    review_words: list[StudyWordOut]
    # 义项卡（equiv_group）：id 是 sense_id，spelling 是锚词，definition 是义项名
    sense_items: list[StudyWordOut] = Field(default_factory=list)
    sense_target: int = 0
    new_target: int
    review_target: int


class AnswerIn(BaseModel):
    """新契约用 kind/target_id/selected_ids；旧契约用 word_id/result，继续兼容。"""

    model_config = ConfigDict(extra="ignore")

    kind: Literal["word", "sense"] = "word"
    target_id: int | None = None
    phase: str | None = None
    selected_ids: list[int] = Field(default_factory=list)
    response_ms: int | None = None
    # 旧契约（自评 / 单选）
    word_id: int | None = None
    result: str | None = None


class AnswerOut(BaseModel):
    status: str
    stability: float | None = None
    difficulty: float | None = None
    due_date: date | None = None
    # 判分结果（作答后回传，可展示漏选/错选）
    result: str | None = None
    selected_correct: int = 0
    correct_total: int = 0
    correct_ids: list[int] = Field(default_factory=list)


class ProgressOut(BaseModel):
    new_target: int
    review_target: int
    new_done: int
    review_done: int


# ---------- 统计 ----------


class StatsOverview(BaseModel):
    total_words: int
    new: int
    learning: int
    reviewing: int
    mastered: int
    streak_days: int
    total_days: int
    learned_today: int


class CalendarDay(BaseModel):
    date: str
    count: int


class RecentDay(BaseModel):
    date: str
    new_count: int
    review_count: int


# ---------- 设置 ----------


class SettingsOut(BaseModel):
    new_per_day: int
    review_per_day: int
    active_book_id: int | None = None


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    new_per_day: int = Field(default=25, ge=5, le=300)
    review_per_day: int = Field(default=50, ge=10, le=600)
    active_book_id: int | None = None
