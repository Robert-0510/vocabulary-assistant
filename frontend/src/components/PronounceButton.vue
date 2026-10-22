<script setup lang="ts">
import { pronounce } from '@/utils/speech'

const props = withDefaults(defineProps<{ word: string; size?: 'default' | 'large' }>(), {
  size: 'default',
})

function play() {
  pronounce(props.word)
}
</script>

<template>
  <el-button
    :size="size"
    circle
    type="primary"
    plain
    :aria-label="`朗读单词 ${word}`"
    :title="`发音（空格键）：${word}`"
    @click.stop="play"
  >
    <el-icon><Microphone /></el-icon>
  </el-button>
</template>
