import client from './client'
import type {
  AnswerResult,
  AppSettings,
  AuthUser,
  Book,
  CalendarDay,
  ImportResult,
  Progress,
  RecentDay,
  StatsOverview,
  TodayTask,
  UploadResult,
  WordPage,
  WordUpdatePayload,
} from './types'

// ---------- 账号 ----------
export function register(payload: { username: string; password: string }): Promise<AuthUser> {
  return client.post('/auth/register', payload) as Promise<AuthUser>
}

export function login(payload: { username: string; password: string }): Promise<AuthUser> {
  return client.post('/auth/login', payload) as Promise<AuthUser>
}

export function logout(): Promise<{ ok: boolean }> {
  return client.post('/auth/logout') as Promise<{ ok: boolean }>
}

export function getMe(): Promise<AuthUser> {
  return client.get('/auth/me', { silent: true }) as Promise<AuthUser>
}

export function deleteAccount(password: string): Promise<{ ok: boolean }> {
  return client.post('/auth/delete-account', { password }) as Promise<{
    ok: boolean
  }>
}

export function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<{ ok: boolean }> {
  return client.post('/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
  }) as Promise<{ ok: boolean }>
}

// ---------- 词书 ----------
export function uploadBook(file: File): Promise<UploadResult> {
  const form = new FormData()
  form.append('file', file)
  return client.post('/books/upload', form) as Promise<UploadResult>
}

export function getBooks(): Promise<Book[]> {
  return client.get('/books') as Promise<Book[]>
}

export function getBookWords(
  bookId: number,
  params: { page: number; page_size: number; keyword?: string; status?: string },
): Promise<WordPage> {
  return client.get(`/books/${bookId}/words`, { params }) as Promise<WordPage>
}

export function deleteBook(bookId: number): Promise<{ ok: boolean }> {
  return client.delete(`/books/${bookId}`) as Promise<{ ok: boolean }>
}

export function activateBook(bookId: number): Promise<{ ok: boolean }> {
  return client.put(`/books/${bookId}/activate`) as Promise<{ ok: boolean }>
}

export function resetBookProgress(bookId: number): Promise<{ ok: boolean; deleted_logs: number }> {
  return client.post(`/books/${bookId}/reset`) as Promise<{
    ok: boolean
    deleted_logs: number
  }>
}

export function updateWord(
  bookId: number,
  wordId: number,
  payload: WordUpdatePayload,
): Promise<{ ok: boolean }> {
  return client.put(`/books/${bookId}/words/${wordId}`, payload) as Promise<{
    ok: boolean
  }>
}

// ---------- 学习 ----------
export function getTodayTask(): Promise<TodayTask> {
  return client.get('/study/today') as Promise<TodayTask>
}

export function submitAnswer(wordId: number, phase: string, result: string): Promise<unknown> {
  return client.post('/study/answer', { word_id: wordId, phase, result })
}

/** 新题型：多选，服务端判分。kind = word（释义）/ sense（等价组）。 */
export function submitMultiAnswer(
  kind: 'word' | 'sense',
  targetId: number,
  phase: string,
  selectedIds: number[],
): Promise<AnswerResult> {
  return client.post('/study/answer', {
    kind,
    target_id: targetId,
    phase,
    selected_ids: selectedIds,
  }) as Promise<AnswerResult>
}

export function getProgress(): Promise<Progress> {
  return client.get('/study/progress') as Promise<Progress>
}

// ---------- 统计 ----------
export function getStatsOverview(): Promise<StatsOverview> {
  return client.get('/stats/overview') as Promise<StatsOverview>
}

export function getCalendar(month: string): Promise<CalendarDay[]> {
  return client.get('/stats/calendar', { params: { month } }) as Promise<CalendarDay[]>
}

export function getRecent(days = 30): Promise<RecentDay[]> {
  return client.get('/stats/recent', { params: { days } }) as Promise<RecentDay[]>
}

// ---------- 设置 ----------
export function getSettings(): Promise<AppSettings> {
  return client.get('/settings') as Promise<AppSettings>
}

export function updateSettings(payload: Partial<AppSettings>): Promise<AppSettings> {
  return client.put('/settings', payload) as Promise<AppSettings>
}

// ---------- 备份 ----------
export function exportBackup(): Promise<Blob> {
  return client.get('/export', { responseType: 'blob' }) as unknown as Promise<Blob>
}

export function importBackup(file: File): Promise<ImportResult> {
  const form = new FormData()
  form.append('file', file)
  return client.post('/import', form) as Promise<ImportResult>
}
