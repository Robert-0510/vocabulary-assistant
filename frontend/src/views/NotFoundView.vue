<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div class="page not-found">
    <el-result icon="warning" title="404" sub-title="页面不存在或已被移动">
      <template #extra>
        <el-button type="primary" size="large" @click="router.push('/')"> 返回首页 </el-button>
        <el-button size="large" @click="router.push('/books')">词书管理</el-button>
      </template>
    </el-result>
  </div>
</template>

<style scoped>
.not-found {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 70vh;
}
</style>
