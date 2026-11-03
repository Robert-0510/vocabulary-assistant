import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getTodayTask, submitMultiAnswer } from '@/api'
import { useStudyStore } from '@/stores/study'
import type { MultiQuiz, StudyWord } from '@/api/types'

vi.mock('@/api', () => ({
  getTodayTask: vi.fn(),
  submitMultiAnswer: vi.fn(),
}))

const mockedGetToday = vi.mocked(getTodayTask)
const mockedSubmitMulti = vi.mocked(submitMultiAnswer)

function multiWord(id: number): StudyWord {
  const quiz: MultiQuiz = {
    type: 'meaning_multi',
    question: `word${id}`,
    options: [
      { id: id * 10 + 1, text: '义项一' },
      { id: id * 10 + 2, text: '义项二' },
      { id: id * 10 + 3, text: '义项三' },
      { id: id * 10 + 4, text: '义项四' },
    ],
    option_count: 4,
  }
  return {
    id,
    spelling: `word${id}`,
    phonetic: '',
    definition: `释义 ${id}`,
    example_en: null,
    example_cn: null,
    status: 'new',
    quiz,
  }
}

function task(newIds: number[], reviewIds: number[]) {
  return {
    new_words: newIds.map(multiWord),
    review_words: reviewIds.map(multiWord),
    sense_items: [],
    sense_target: 0,
    new_target: newIds.length,
    review_target: reviewIds.length,
  }
}

const gradedCorrect = {
  status: 'reviewing',
  stability: 1,
  difficulty: 4,
  due_date: null,
  result: 'correct',
  selected_correct: 1,
  correct_total: 1,
  correct_ids: [21],
}

describe('study store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockedGetToday.mockReset()
    mockedSubmitMulti.mockReset()
    mockedSubmitMulti.mockResolvedValue(gradedCorrect)
  })

  it('interleaves reviews and new words in the documented 2:1 order', async () => {
    mockedGetToday.mockResolvedValue(task([1, 2, 3], [4, 5]))
    const store = useStudyStore()
    await store.loadToday()
    // 2 张复习 + 1 张新词交替
    expect(store.queue.map((item) => item.kind)).toEqual([
      'review',
      'review',
      'new',
      'new',
      'new',
    ])
  })

  it('new words show the definition first, then the multi-select quiz', async () => {
    mockedGetToday.mockResolvedValue(task([1], []))
    const store = useStudyStore()
    await store.loadToday()
    expect(store.current?.step).toBe('detail')
    store.continueNext()
    expect(store.current?.step).toBe('meaning')

    await store.answerMulti([11])
    expect(mockedSubmitMulti).toHaveBeenCalledWith('word', 1, 'new_quiz', [11])
    store.continueAfterMulti()
    expect(store.newDone).toBe(1)
    expect(store.finished).toBe(true)
  })

  it('wrong answers are requeued once', async () => {
    mockedSubmitMulti.mockResolvedValue({ ...gradedCorrect, result: 'wrong' })
    mockedGetToday.mockResolvedValue(task([1], []))
    const store = useStudyStore()
    await store.loadToday()
    store.continueNext()
    await store.answerMulti([11])
    store.continueAfterMulti()
    expect(store.queue.length).toBe(2)
    expect(store.queue[1].isRequeued).toBe(true)
  })

  it('queues a group item right after its representative word', async () => {
    const sense = multiWord(2)
    const senseQuiz = sense.quiz as MultiQuiz
    senseQuiz.type = 'equiv_group'
    senseQuiz.owner_word_id = 1
    mockedGetToday.mockResolvedValue({
      ...task([1], []),
      sense_items: [sense],
      sense_target: 1,
    })
    const store = useStudyStore()
    await store.loadToday()
    expect(store.queue.map((item) => item.kind)).toEqual(['new', 'sense'])

    store.continueNext()
    await store.answerMulti([11])
    store.continueAfterMulti()
    expect(store.current?.kind).toBe('sense')
    expect(store.current?.step).toBe('group')
  })
})
