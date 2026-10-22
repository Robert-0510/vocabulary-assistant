import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getTodayTask, submitAnswer } from '@/api'
import { useStudyStore } from '@/stores/study'
import type { StudyWord } from '@/api/types'

vi.mock('@/api', () => ({
  getTodayTask: vi.fn(),
  submitAnswer: vi.fn(),
}))

const mockedGetToday = vi.mocked(getTodayTask)
const mockedSubmit = vi.mocked(submitAnswer)

function word(id: number): StudyWord {
  return {
    id,
    spelling: `word${id}`,
    phonetic: '',
    definition: `释义 ${id}`,
    example_en: null,
    example_cn: null,
    status: 'new',
    quiz: {
      type: 'en2cn',
      question: `word${id}`,
      options: ['a', 'b', 'c', 'd'],
      answer_index: 0,
    },
  }
}

function task(newIds: number[], reviewIds: number[]) {
  return {
    new_words: newIds.map(word),
    review_words: reviewIds.map(word),
    new_target: newIds.length,
    review_target: reviewIds.length,
  }
}

describe('study store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockedGetToday.mockReset()
    mockedSubmit.mockReset()
    mockedSubmit.mockResolvedValue(undefined)
  })

  it('interleaves reviews and new words in the documented 2:1 order', async () => {
    mockedGetToday.mockResolvedValue(task([1, 2], [11, 12, 13, 14]))
    const store = useStudyStore()
    await store.loadToday()

    expect(store.queue.map((item) => item.word.id)).toEqual([11, 12, 1, 13, 14, 2])
    expect(store.current?.step).toBe('quiz')
  })

  it('maps 400 to noBook and 500 to a real error', async () => {
    mockedGetToday.mockRejectedValueOnce({ response: { status: 400 } })
    const store = useStudyStore()
    await store.loadToday()
    expect(store.noBook).toBe(true)
    expect(store.error).toBe(false)

    mockedGetToday.mockRejectedValueOnce({ response: { status: 500 } })
    await store.loadToday()
    expect(store.noBook).toBe(false)
    expect(store.error).toBe(true)
  })

  it('unknown self-rating leads to the quiz, know advances directly', async () => {
    mockedGetToday.mockResolvedValue(task([1], []))
    const store = useStudyStore()
    await store.loadToday()

    await store.answerIntro('unknown')
    expect(store.current?.step).toBe('detail')
    expect(store.current?.detailNext).toBe('quiz')

    store.continueNext()
    expect(store.current?.step).toBe('quiz')

    // 重置为「认识」路径
    setActivePinia(createPinia())
    const store2 = useStudyStore()
    mockedGetToday.mockResolvedValue(task([2], []))
    await store2.loadToday()
    await store2.answerIntro('know')
    expect(store2.current?.detailNext).toBe('advance')
    store2.continueNext()
    expect(store2.current).toBeUndefined()
    expect(store2.finished).toBe(true)
  })

  it('correct new-word quiz schedules a recheck and graduates the original item', async () => {
    vi.useFakeTimers()
    try {
      mockedGetToday.mockResolvedValue(task([1], []))
      const store = useStudyStore()
      await store.loadToday()
      await store.answerIntro('unknown')
      store.continueNext()

      const pending = store.answerQuiz(0)
      await vi.advanceTimersByTimeAsync(800)
      await pending

      expect(store.current?.step).toBe('recheck')
      expect(store.queue.length).toBe(2)
      expect(store.graduated).toBe(1)
      expect(mockedSubmit).toHaveBeenCalledWith(1, 'new_quiz', 'correct')
    } finally {
      vi.useRealTimers()
    }
  })
})
