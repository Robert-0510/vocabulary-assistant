/**
 * 学习会话状态机（2026-11 新版）：
 * - 新词：先看释义 → 不定项选择 → 服务端判分
 * - 复习词：直接不定项选择
 * - 等价组：紧跟所属代表词之后，多选同义成员
 * 旧的自评三键与 en2cn/cn2en/cloze 题型已下线。
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { getTodayTask, submitMultiAnswer } from '@/api'
import type { GradedAnswer, MultiQuiz, MultiResult, StudyWord } from '@/api/types'

export interface QueueItem {
  key: string
  word: StudyWord
  kind: 'new' | 'review' | 'sense'
  step: 'detail' | 'meaning' | 'group'
  isRequeued: boolean
}

let uid = 0

function isMultiQuiz(quiz: StudyWord['quiz']): quiz is MultiQuiz {
  return !!quiz && (quiz.type === 'meaning_multi' || quiz.type === 'equiv_group')
}

function initialStep(kind: QueueItem['kind']): QueueItem['step'] {
  if (kind === 'sense') return 'group'
  return kind === 'new' ? 'detail' : 'meaning'
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
      !error.value &&
      pos.value >= queue.value.length &&
      queue.value.length > 0,
  )
  const progressPct = computed(() =>
    totalGraduate.value === 0
      ? 0
      : Math.round((graduated.value / totalGraduate.value) * 100),
  )

  function makeItem(word: StudyWord, kind: QueueItem['kind'], isRequeued = false): QueueItem {
    return {
      key: `${kind[0]}${word.id}-${++uid}`,
      word,
      kind,
      step: initialStep(kind),
      isRequeued,
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
    // 等价组题按代表词归位：先出代表词的词题，再出它的组题
    const groups = new Map<number, StudyWord[]>()
    const orphans: StudyWord[] = []
    for (const sense of senseItems) {
      const owner = (sense.quiz as MultiQuiz | null)?.owner_word_id
      if (owner == null) {
        orphans.push(sense)
        continue
      }
      const list = groups.get(owner) ?? []
      list.push(sense)
      groups.set(owner, list)
    }
    const pushWord = (word: StudyWord, kind: QueueItem['kind']) => {
      if (!word.quiz) return // 没有义项数据/干扰项不足的词跳过，避免卡在队首
      items.push(makeItem(word, kind))
      for (const sense of groups.get(word.id) ?? []) items.push(makeItem(sense, 'sense'))
      groups.delete(word.id)
    }
    // 2 张复习 + 1 张新词交替出牌；组题紧跟所属代表词
    while (n.length || r.length) {
      for (let i = 0; i < 2 && r.length; i++) pushWord(r.shift()!, 'review')
      if (n.length) pushWord(n.shift()!, 'new')
    }
    // 兜底：代表词不在今日池里时，组题仍要出（追加在末尾）
    for (const rest of groups.values()) {
      for (const sense of rest) items.push(makeItem(sense, 'sense'))
    }
    for (const sense of orphans) items.push(makeItem(sense, 'sense'))
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

  /** 多选作答：多选释义 / 等价组，服务端判分 */
  async function answerMulti(ids: number[]) {
    const item = current.value
    const quiz = item?.word.quiz
    if (!item || busy.value || graded.value || !quiz || !isMultiQuiz(quiz)) return
    busy.value = true
    try {
      const isSense = item.kind === 'sense'
      // 词级多选沿用生命周期 phase（new_quiz / review），保证今日进度统计口径一致；
      // 等价组用 group（服务端只更新代表词的词卡）。
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
        step: initialStep(item.kind),
        isRequeued: true,
      })
    }
  }

  /** 新词详情卡的「继续」：进入不定项选择 */
  function continueNext() {
    const item = current.value
    if (!item || busy.value) return
    if (item.step === 'detail') item.step = 'meaning'
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
    answerMulti,
    continueAfterMulti,
    continueNext,
  }
})
