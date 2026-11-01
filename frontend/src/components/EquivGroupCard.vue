<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { GradedAnswer, MultiQuiz, StudyWord } from '@/api/types'
import { pronounce } from '@/utils/speech'
import PronounceButton from './PronounceButton.vue'
import SenseResultPanel from './SenseResultPanel.vue'

const props = defineProps<{
  word: StudyWord
  quiz: MultiQuiz
  label: string
  graded: GradedAnswer | null
}>()

const emit = defineEmits<{ submit: [ids: number[]]; next: [] }>()

const selected = ref<Set<number>>(new Set())

watch(
  () => props.quiz,
  () => {
    selected.value = new Set()
  },
)

const selectedIds = computed(() => [...selected.value])
const canSubmit = computed(() => !props.graded && selected.value.size > 0)

const optionTextById = computed(
  () => new Map(props.quiz.options.map((option) => [option.id, option.text])),
)
const missed = computed(() => {
  if (!props.graded) return []
  return props.graded.correctIds
    .filter((id) => !props.graded!.selectedIds.includes(id))
    .map((id) => optionTextById.value.get(id) ?? String(id))
})
const wrongPicked = computed(() => {
  if (!props.graded) return []
  return props.graded.selectedIds
    .filter((id) => !props.graded!.correctIds.includes(id))
    .map((id) => optionTextById.value.get(id) ?? String(id))
})

function toggle(id: number) {
  if (props.graded) return
  const next = new Set(selected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selected.value = next
}

function optionType(id: number): 'default' | 'primary' | 'success' | 'danger' {
  if (props.graded) {
    if (props.graded.correctIds.includes(id)) return 'success'
    if (props.graded.selectedIds.includes(id)) return 'danger'
    return 'default'
  }
  return selected.value.has(id) ? 'primary' : 'default'
}

function submit() {
  if (!canSubmit.value) return
  emit('submit', selectedIds.value)
}

function onKey(e: KeyboardEvent) {
  if (e.code === 'Space') {
    e.preventDefault()
    pronounce(props.word.spelling)
    return
  }
  if (props.graded) {
    if (e.key === 'Enter') emit('next')
    return
  }
  const n = Number(e.key)
  if (n >= 1 && n <= props.quiz.options.length) {
    e.preventDefault()
    toggle(props.quiz.options[n - 1].id)
    return
  }
  if (e.key === 'Enter') {
    e.preventDefault()
    submit()
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKey)
  setTimeout(() => pronounce(props.word.spelling), 150)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="equiv-card">
    <div class="quiz-head">
      <el-tag type="warning" effect="plain">{{ label }}</el-tag>
      <span class="type-label text-muted">选出与它同义的词（可多选）</span>
    </div>

    <div class="question">
      <div class="q-word">
        <span class="spelling">{{ word.spelling }}</span>
        <PronounceButton :word="word.spelling" size="large" />
      </div>
      <div v-if="word.phonetic" class="phonetic">{{ word.phonetic }}</div>
      <p class="sense">{{ word.definition }}</p>
    </div>

    <div class="options" role="group" aria-label="同义词选项">
      <el-button
        v-for="(option, i) in quiz.options"
        :key="option.id"
        class="option"
        :type="optionType(option.id)"
        :plain="!graded && !selected.has(option.id)"
        :aria-pressed="selected.has(option.id)"
        :data-option-id="option.id"
        size="large"
        @click="toggle(option.id)"
      >
        <span class="opt-index">{{ i + 1 }}</span>
        <span class="opt-text">{{ option.text }}</span>
      </el-button>
    </div>

    <div class="actions">
      <el-button
        type="primary"
        size="large"
        :disabled="!canSubmit"
        data-test="submit"
        @click="submit"
      >
        确定 <span class="kbd-hint">回车</span>
      </el-button>
    </div>

    <SenseResultPanel
      v-if="graded"
      :result="graded.result"
      :selected-correct="graded.selectedCorrect"
      :correct-total="graded.correctTotal"
      :missed="missed"
      :wrong-picked="wrongPicked"
      @next="emit('next')"
    />
  </div>
</template>

<style scoped>
.equiv-card {
  text-align: center;
}
.quiz-head {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 14px;
}
.type-label {
  font-size: 13px;
}
.question {
  min-height: 108px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
}
.q-word {
  display: flex;
  align-items: center;
  gap: 14px;
}
.spelling {
  font-size: 40px;
  font-weight: 700;
  color: #303133;
}
.phonetic {
  color: #909399;
  margin-top: 6px;
}
.sense {
  color: #409eff;
  font-size: 16px;
  font-weight: 600;
  margin: 10px 0 0;
}
.options {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 14px;
}
.option {
  height: auto;
  min-height: 56px;
  justify-content: flex-start;
  padding: 8px 14px;
  white-space: normal;
}
.opt-index {
  flex: none;
  width: 22px;
  height: 22px;
  line-height: 22px;
  border: 1px solid currentColor;
  border-radius: 50%;
  font-size: 12px;
  margin-right: 10px;
}
.opt-text {
  font-size: 17px;
  font-weight: 500;
  overflow-wrap: anywhere;
}
.actions {
  margin-top: 16px;
}

@media (max-width: 640px) {
  .spelling {
    font-size: clamp(30px, 10vw, 40px);
  }
  .options {
    grid-template-columns: 1fr;
    gap: 10px;
  }
  .actions .el-button {
    width: 100%;
  }
}
</style>
