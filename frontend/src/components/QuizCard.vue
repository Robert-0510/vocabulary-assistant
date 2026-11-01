<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { LegacyQuiz, StudyWord } from '@/api/types'
import { pronounce } from '@/utils/speech'
import PronounceButton from './PronounceButton.vue'

const props = defineProps<{
  word: StudyWord
  quiz: LegacyQuiz
  label: string
}>()

const emit = defineEmits<{ answered: [idx: number]; next: [] }>()

const selected = ref<number | null>(null)

watch(
  () => props.quiz,
  () => {
    selected.value = null
  },
)

function pick(idx: number) {
  if (selected.value !== null || idx >= props.quiz.options.length) return
  selected.value = idx
  emit('answered', idx)
}

const isCorrect = () => selected.value === props.quiz.answer_index

function onKey(e: KeyboardEvent) {
  if (e.code === 'Space') {
    e.preventDefault()
    pronounce(props.word.spelling)
    return
  }
  if (selected.value === null) {
    const n = Number(e.key)
    if (n >= 1 && n <= props.quiz.options.length) pick(n - 1)
  } else if (!isCorrect() && e.key === 'Enter') {
    emit('next')
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKey)
  if (props.quiz.type === 'en2cn') {
    // 看英选中：自动读一遍单词
    setTimeout(() => pronounce(props.word.spelling), 150)
  }
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

const TYPE_LABEL: Record<string, string> = {
  en2cn: '看英文，选释义',
  cn2en: '看释义，选单词',
  cloze: '补全例句',
}
</script>

<template>
  <div class="quiz-card">
    <div class="quiz-head">
      <el-tag :type="label === '快速复查' ? 'warning' : 'info'" effect="plain">{{ label }}</el-tag>
      <span class="type-label text-muted">{{ TYPE_LABEL[quiz.type] }}</span>
    </div>

    <!-- 题干 -->
    <div v-if="quiz.type === 'en2cn'" class="question en2cn">
      <div class="q-word">
        <span class="spelling">{{ quiz.question }}</span>
        <PronounceButton :word="quiz.question" size="large" />
      </div>
      <div v-if="word.phonetic" class="phonetic">{{ word.phonetic }}</div>
    </div>
    <div v-else-if="quiz.type === 'cloze'" class="question cloze">
      <p class="sentence">{{ quiz.question }}</p>
      <p v-if="selected !== null && word.example_cn" class="example-cn">{{ word.example_cn }}</p>
    </div>
    <div v-else class="question cn2en">
      <p class="definition">{{ quiz.question }}</p>
    </div>

    <!-- 选项 -->
    <div class="options">
      <el-button
        v-for="(opt, i) in quiz.options"
        :key="i"
        class="option"
        :type="
          selected === null
            ? 'default'
            : i === quiz.answer_index
              ? 'success'
              : i === selected
                ? 'danger'
                : 'default'
        "
        :plain="selected === null"
        :aria-pressed="selected === i"
        size="large"
        @click="pick(i)"
      >
        <span class="opt-index">{{ i + 1 }}</span>
        <span class="opt-text">{{ opt }}</span>
      </el-button>
    </div>

    <!-- 反馈 -->
    <div
      v-if="selected !== null"
      class="feedback"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <template v-if="isCorrect()">
        <el-text type="success" size="large">✓ 回答正确</el-text>
      </template>
      <template v-else>
        <el-text type="danger" size="large">
          ✗ 回答错误，正确答案：{{ quiz.options[quiz.answer_index] }}
        </el-text>
        <el-button type="primary" size="large" class="next-btn" @click="emit('next')">
          继续 <span class="kbd-hint">回车</span>
        </el-button>
      </template>
    </div>
  </div>
</template>

<style scoped>
.quiz-card {
  text-align: center;
}
.quiz-head {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-bottom: 14px;
}
.type-label {
  font-size: 13px;
}

.question {
  min-height: 110px;
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
.sentence {
  font-size: 20px;
  color: #303133;
  line-height: 1.8;
  margin: 0 8px;
}
.example-cn {
  color: #909399;
  font-size: 14px;
}
.definition {
  font-size: 22px;
  color: #409eff;
  font-weight: 600;
  margin: 0 8px;
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
  font-size: 16px;
}

.feedback {
  margin-top: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  min-height: 44px;
}
.next-btn {
  margin-left: 12px;
}

@media (max-width: 640px) {
  .spelling {
    font-size: clamp(30px, 10vw, 40px);
  }
  .sentence {
    font-size: 17px;
    margin: 0;
  }
  .definition {
    font-size: 18px;
    margin: 0;
  }
  .options {
    grid-template-columns: 1fr;
    gap: 10px;
  }
  .feedback {
    flex-direction: column;
  }
  .next-btn {
    margin-left: 0;
    width: 100%;
  }
}
</style>
