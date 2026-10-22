<script setup lang="ts">
import { computed } from 'vue'
import type { StudyWord } from '@/api/types'
import PronounceButton from './PronounceButton.vue'

const props = defineProps<{ word: StudyWord }>()

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** 例句中高亮目标单词（先转义再标注） */
const exampleHtml = computed(() => {
  if (!props.word.example_en) return ''
  const escaped = escapeHtml(props.word.example_en)
  const re = new RegExp(`\\b${escapeRegExp(props.word.spelling)}\\b`, 'gi')
  return escaped.replace(re, (m) => `<span class="word-highlight">${m}</span>`)
})
</script>

<template>
  <div class="detail-card">
    <div class="head">
      <h1 class="spelling">{{ word.spelling }}</h1>
      <PronounceButton :word="word.spelling" size="large" />
    </div>
    <div v-if="word.phonetic" class="phonetic">{{ word.phonetic }}</div>
    <div class="definition">{{ word.definition }}</div>
    <el-divider v-if="exampleHtml" />
    <div v-if="exampleHtml" class="example">
      <p class="example-en" v-html="exampleHtml" />
      <p v-if="word.example_cn" class="example-cn">{{ word.example_cn }}</p>
    </div>
  </div>
</template>

<style scoped>
.detail-card {
  text-align: center;
  padding: 8px 4px;
}
.head {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
}
.spelling {
  margin: 0;
  font-size: 44px;
  font-weight: 700;
  color: #303133;
}
.phonetic {
  color: #909399;
  font-size: 16px;
  margin-top: 4px;
}
.definition {
  font-size: 20px;
  color: #409eff;
  margin-top: 18px;
  font-weight: 600;
}
.example {
  margin-top: 4px;
}
.example-en {
  font-size: 16px;
  color: #606266;
  line-height: 1.7;
}
.example-cn {
  font-size: 14px;
  color: #909399;
  margin-top: 2px;
}
</style>
