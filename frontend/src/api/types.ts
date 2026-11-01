export interface AuthUser {
  id: number
  username: string
}

export interface BookCounts {
  new: number
  learning: number
  reviewing: number
  mastered: number
}

export interface Book {
  id: number
  name: string
  description: string | null
  word_count: number
  created_at: string
  is_active: boolean
  counts: BookCounts
}

export interface UploadResult {
  book_id: number
  name: string
  imported: number
  skipped: number
}

export interface WordRow {
  id: number
  spelling: string
  phonetic: string
  definition: string
  example_en: string | null
  example_cn: string | null
  seq: number
  status: string
  interval_days: number
  stability: number | null
  difficulty: number | null
  reps: number
  lapses: number
  due_date: string | null
}

export interface WordPage {
  total: number
  items: WordRow[]
}

export interface QuizOption {
  id: number
  text: string
}

/** 旧题型：前端本地判分（词书没有义项数据时的兜底）。 */
export interface LegacyQuiz {
  type: 'en2cn' | 'cn2en' | 'cloze'
  question: string
  options: string[]
  answer_index: number
}

/** 新题型：服务端判分，响应不含正确集合。 */
export interface MultiQuiz {
  type: 'meaning_multi' | 'equiv_group'
  question: string
  options: QuizOption[]
  option_count: number
}

export type Quiz = LegacyQuiz | MultiQuiz

export interface StudyWord {
  id: number
  spelling: string
  phonetic: string
  definition: string
  example_en: string | null
  example_cn: string | null
  status: string
  quiz: Quiz | null
}

export interface TodayTask {
  new_words: StudyWord[]
  review_words: StudyWord[]
  sense_items: StudyWord[]
  sense_target: number
  new_target: number
  review_target: number
}

export type MultiResult = 'correct' | 'partial' | 'wrong'

/** 服务端判分结果（作答后回传，用于结果面板展示漏选/错选）。 */
export interface GradedAnswer {
  result: MultiResult
  selectedIds: number[]
  correctIds: number[]
  correctTotal: number
  selectedCorrect: number
}

export interface AnswerResult {
  status: string
  stability: number | null
  difficulty: number | null
  due_date: string | null
  result: string | null
  selected_correct: number
  correct_total: number
  correct_ids: number[]
}

export interface Progress {
  new_target: number
  review_target: number
  new_done: number
  review_done: number
}

export interface StatsOverview {
  total_words: number
  new: number
  learning: number
  reviewing: number
  mastered: number
  streak_days: number
  total_days: number
  learned_today: number
}

export interface CalendarDay {
  date: string
  count: number
}

export interface RecentDay {
  date: string
  new_count: number
  review_count: number
}

export interface AppSettings {
  new_per_day: number
  review_per_day: number
  active_book_id: number | null
}

export interface ImportResult {
  books_imported: number
  words_imported: number
  skipped: number
}

export interface WordUpdatePayload {
  spelling?: string
  phonetic?: string
  definition?: string
  example_en?: string | null
  example_cn?: string | null
}
