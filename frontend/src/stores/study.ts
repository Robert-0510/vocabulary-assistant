/**
 * 学习会话状态机（扇贝风格）：
 * - 新词（旧题型）：自评三键 →（不认识）详情 → 测试 → 队尾快速复查
 * - 新词（多选释义）：先看释义 → 多选义项 → 服务端判分
 * - 复习词：直接测试 → 答错看详情后回队尾重学
 * - 义项卡：等价组多选（锚词 + 同义成员 + 干扰项）
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { getTodayTask, submitAnswer, submitMultiAnswer } from '@/api'
import type { GradedAnswer, MultiQuiz, MultiResult, StudyWord } from '@/api/types'

export interface QueueItem {
  key: string
  word: StudyWord
  kind: 'new' | 'review' | 'sense'
  step: 'intro' | 'detail' | 'quiz' | 'recheck' | 'meaning' | 'group'
  isRequeued: boolean
  detailNext: 'quiz' | 'recheck' | 'requeue' | 'advance'
}

let uid = 0
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

function isMultiQuiz(quiz: StudyWord['quiz']): quiz is MultiQuiz {
  return quiz?.type === 'meaning_multi' || quiz?.type === 'equiv_group'
}

function initialStep(kind: QueueItem['kind'], word: StudyWord): QueueItem['step'] {
  if (kind === 'sense') return 'group'
  if (isMultiQuiz(word.quiz)) return kind === 'new' ? 'detail' : 'meaning'
  return kind === 'new' ? 'intro' : 'quiz'
}

export const useStudyStore = defineStore('study', () => {
  const loading = ref(false)
  const noBook = ref(false)
  const emptyToday = ref(false)
  const error = ref(false)
  const queue = ref<QueueItem[]>([])
  const pos = ref(0)
  const busy = ref(false)
  const graded = ref<GradedAnswer | null>(null)

  const newTarget = ref(0)
  const reviewTarget = ref(0)
  const senseTarget = ref(0)
  const newDone = ref(0)
  const reviewDone = ref(0)
  const senseDone = ref(0)
  const graduated = ref(0)
  const totalGraduate = ref(0)

  const current = computed<QueueItem | undefined>(() => queue.value[pos.value])
  const finished = computed(
    () =>
      !loading.value &&
      !noBook.value &&
      !emptyToday.value &&
      !error.value &&
      pos.value >= queue.value.length &&
      queue.value.length > 0,
  )
  const progressPct = computed(() =>
    totalGraduate.value === 0 ? 0 : Math.round((graduated.value / totalGraduate.value) * 100),
  )

  function makeItem(word: StudyWord, kind: QueueItem['kind'], isRequeued = false): QueueItem {
    return {
      key: `${kind[0]}${word.id}-${++uid}`,
      word,
      kind,
      step: initialStep(kind, word),
      isRequeued,
      detailNext: kind === 'new' ? 'quiz' : 'requeue',
    }
  }

  function buildQueue(
    newWords: StudyWord[],
    reviewWords: StudyWord[],
    senseItems: StudyWord[],
  ): QueueItem[] {
    const items: QueueItem[] = []
    const n = [...newWords]
    const r = [...reviewWords]
    const s = [...senseItems]
    // 新词 : 复习 ≈ 1 : 2 交替出牌；每两张牌后插一道义项卡
    while (n.length || r.length || s.length) {
      for (let i = 0; i < 2 && r.length; i++) {
        items.push(makeItem(r.shift()!, 'review'))
      }
      if (s.length) items.push(makeItem(s.shift()!, 'sense'))
      if (n.length) items.push(makeItem(n.shift()!, 'new'))
    }
    return items
  }

  async function loadToday() {
    loading.value = true
    noBook.value = false
    emptyToday.value = false
    error.value = false
    queue.value = []
    pos.value = 0
    graded.value = null
    graduated.value = 0
    totalGraduate.value = 0
    newDone.value = 0
    reviewDone.value = 0
    senseDone.value = 0
    try {
      const t = await getTodayTask()
      newTarget.value = t.new_target
      reviewTarget.value = t.review_target
      senseTarget.value = t.sense_target ?? t.sense_items?.length ?? 0
      queue.value = buildQueue(t.new_words, t.review_words, t.sense_items ?? [])
      totalGraduate.value = queue.value.length
      if (!queue.value.length) emptyToday.value = true
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 400) noBook.value = true
      else error.value = true // 服务异常不能伪装成「今日已完成」
    } finally {
      loading.value = false
    }
  }

  function graduate(item: QueueItem) {
    if (item.isRequeued) return // 克隆重排队项毕业不再计数
    graduated.value++
    if (item.kind === 'new') newDone.value++
    else if (item.kind === 'review') reviewDone.value++
    else senseDone.value++
  }

  function pushRelearnClone(item: QueueItem) {
    queue.value.push({
      key: `L${item.word.id}-${++uid}`,
      word: item.word,
      kind: 'review',
      step: isMultiQuiz(item.word.quiz) ? 'meaning' : 'quiz',
      isRequeued: true,
      detailNext: 'requeue',
    })
  }

  /** 新词首见自评：认识 / 不认识 / 熟知（仅旧题型路径） */
  async function answerIntro(result: 'know' | 'unknown' | 'master') {
    const item = current.value
    if (!item || busy.value) return
    busy.value = true
    try {
      await submitAnswer(item.word.id, 'new_first', result)
      // 三种自评都先展示释义：
      // 不认识 → 例句挖空测试；认识/熟知 → 看完释义直接进入下一个
      item.step = 'detail'
      item.detailNext = result === 'unknown' ? 'quiz' : 'advance'
    } finally {
      busy.value = false
    }
  }

  /** 旧题型作答（新词测试 / 复习测试 / 重学 / 快速复查） */
  async function answerQuiz(idx: number) {
    const item = current.value
    const quiz = item?.word.quiz
    if (!item || busy.value || !quiz || isMultiQuiz(quiz)) return
    busy.value = true
    try {
      const correct = idx === quiz.answer_index
      if (item.step === 'recheck') {
        // 快速复查不重复提交（状态已在首次测试时更新）
        if (correct) {
          await sleep(800)
          graduate(item)
          pos.value++
        }
        return
      }
      const phase = item.kind === 'new' ? 'new_quiz' : item.isRequeued ? 'relearn' : 'review'
      await submitAnswer(item.word.id, phase, correct ? 'correct' : 'wrong')
      if (correct) {
        await sleep(800)
        graduate(item)
        if (item.kind === 'new' && !item.isRequeued) {
          // 新词答对 → 队尾安排一次快速复查
          queue.value.push({
            key: `C${item.word.id}-${++uid}`,
            word: item.word,
            kind: 'new',
            step: 'recheck',
            isRequeued: true,
            detailNext: 'recheck',
          })
        }
        pos.value++
      }
    } finally {
      busy.value = false
    }
  }

  /** 新题型作答：多选释义 / 等价组，服务端判分 */
  async function answerMulti(ids: number[]) {
    const item = current.value
    const quiz = item?.word.quiz
    if (!item || busy.value || graded.value || !quiz || !isMultiQuiz(quiz)) return
    busy.value = true
    try {
      const isSense = item.kind === 'sense'
      // 词级多选沿用生命周期 phase（new_quiz / review），保证今日进度统计口径一致；
      // 义项卡用 group。服务端同时接受 meaning，供其他客户端显式标注多选释义。
      const phase = isSense
        ? 'group'
        : item.kind === 'new'
          ? 'new_quiz'
          : item.isRequeued
            ? 'relearn'
            : 'review'
      const result = await submitMultiAnswer(isSense ? 'sense' : 'word', item.word.id, phase, ids)
      graded.value = {
        result: (result.result ?? 'wrong') as MultiResult,
        selectedIds: ids,
        correctIds: result.correct_ids ?? [],
        correctTotal: result.correct_total ?? 0,
        selectedCorrect: result.selected_correct ?? 0,
      }
    } finally {
      busy.value = false
    }
  }

  /** 多选结果面板的「继续」：全对出队；漏选/错选回队尾再练一次 */
  function continueAfterMulti() {
    const item = current.value
    const result = graded.value?.result
    if (!item || !result) return
    graded.value = null
    if (result === 'correct') graduate(item)
    pos.value++
    if (result !== 'correct' && !item.isRequeued) {
      queue.value.push({
        key: `M${item.word.id}-${++uid}`,
        word: item.word,
        kind: item.kind,
        step: item.kind === 'sense' ? 'group' : 'meaning',
        isRequeued: true,
        detailNext: 'requeue',
      })
    }
  }

  /** 继续按钮：详情卡继续 / 答错后的继续 */
  function continueNext() {
    const item = current.value
    if (!item || busy.value) return
    if (item.step === 'detail') {
      if (item.detailNext === 'quiz') {
        item.step = isMultiQuiz(item.word.quiz) ? 'meaning' : 'quiz'
      } else if (item.detailNext === 'recheck') item.step = 'recheck'
      else if (item.detailNext === 'advance') {
        // 认识/熟知：看完释义直接出队
        graduate(item)
        pos.value++
      } else {
        // 复习词答错：本项出队，克隆到队尾重学
        graduate(item)
        pos.value++
        pushRelearnClone(item)
      }
    } else {
      // 测试答错，先看详情再继续
      item.detailNext =
        item.step === 'recheck' ? 'recheck' : item.kind === 'new' ? 'quiz' : 'requeue'
      item.step = 'detail'
    }
  }

  return {
    loading,
    noBook,
    emptyToday,
    error,
    queue,
    pos,
    busy,
    graded,
    newTarget,
    reviewTarget,
    senseTarget,
    newDone,
    reviewDone,
    senseDone,
    graduated,
    totalGraduate,
    current,
    finished,
    progressPct,
    loadToday,
    answerIntro,
    answerQuiz,
    answerMulti,
    continueAfterMulti,
    continueNext,
  }
})
