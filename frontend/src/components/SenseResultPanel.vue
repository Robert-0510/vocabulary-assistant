<script setup lang="ts">
import { computed } from 'vue'
import type { MultiResult } from '@/api/types'

const props = defineProps<{
  result: MultiResult
  selectedCorrect: number
  correctTotal: number
  missed: string[]
  wrongPicked: string[]
}>()

const emit = defineEmits<{ next: [] }>()

const headline = computed(() => {
  if (props.result === 'correct') {
    return `✓ 全部选对（${props.correctTotal}/${props.correctTotal}）`
  }
  if (props.result === 'partial') {
    return `◐ 部分正确（选中 ${props.selectedCorrect}/${props.correctTotal}）`
  }
  return '✗ 全部选错'
})
</script>

<template>
  <div
    class="sense-result"
    role="status"
    aria-live="polite"
    aria-atomic="true"
    data-test="sense-result"
  >
    <el-text
      size="large"
      class="headline"
      :type="result === 'correct' ? 'success' : result === 'partial' ? 'warning' : 'danger'"
    >
      {{ headline }}
    </el-text>

    <div v-if="missed.length" class="tag-row" data-test="missed">
      <span class="tag-label">漏选</span>
      <el-tag v-for="text in missed" :key="text" type="warning" effect="plain" disable-transitions>
        {{ text }}
      </el-tag>
    </div>
    <div v-if="wrongPicked.length" class="tag-row" data-test="wrong-picked">
      <span class="tag-label">错选</span>
      <el-tag
        v-for="text in wrongPicked"
        :key="text"
        type="danger"
        effect="plain"
        disable-transitions
      >
        {{ text }}
      </el-tag>
    </div>

    <el-button type="primary" size="large" class="next-btn" @click="emit('next')">
      继续 <span class="kbd-hint">回车</span>
    </el-button>
  </div>
</template>

<style scoped>
.sense-result {
  margin-top: 18px;
  padding: 14px 16px;
  border-radius: 10px;
  background: #f7f8fa;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}
.headline {
  font-weight: 600;
}
.tag-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 8px;
  max-width: 100%;
}
.tag-row :deep(.el-tag) {
  height: auto;
  max-width: 100%;
  white-space: normal;
  overflow-wrap: anywhere;
  line-height: 1.4;
  padding: 2px 8px;
}
.tag-label {
  font-size: 13px;
  color: #909399;
}
.next-btn {
  margin-top: 4px;
}

@media (max-width: 640px) {
  .sense-result {
    padding: 12px;
  }
  .next-btn {
    width: 100%;
  }
}
</style>
