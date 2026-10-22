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

export interface Quiz {
  type: 'en2cn' | 'cn2en' | 'cloze'
  question: string
  options: string[]
  answer_index: number
}

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
  new_target: number
  review_target: number
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
