<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  changePassword,
  exportBackup,
  getBooks,
  getSettings,
  importBackup,
  updateSettings,
} from '@/api'
import type { Book } from '@/api/types'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const newPerDay = ref(25)
const reviewPerDay = ref(50)
const activeBookId = ref<number | null>(null)
const books = ref<Book[]>([])
const saving = ref(false)

const passwordForm = reactive({ current: '', next: '', confirm: '' })
const passwordSaving = ref(false)
const exportLoading = ref(false)
const importLoading = ref(false)
const importInput = ref<HTMLInputElement>()

/** 预设档位（新词 : 复习 = 1 : 2） */
const TIERS = [
  { label: '入门', new: 25, review: 50, desc: '轻松入门' },
  { label: '轻松', new: 50, review: 100, desc: '日常保持' },
  { label: '标准', new: 75, review: 150, desc: '稳步提升' },
  { label: '进阶', new: 100, review: 200, desc: '认真备考' },
  { label: '强化', new: 150, review: 300, desc: '冲刺提分' },
  { label: '高强度', new: 200, review: 400, desc: '极限挑战' },
]

const matchedTier = computed(() =>
  TIERS.find((t) => t.new === newPerDay.value && t.review === reviewPerDay.value),
)

function applyTier(t: (typeof TIERS)[number]) {
  newPerDay.value = t.new
  reviewPerDay.value = t.review
}

async function refreshAll() {
  const [s, b] = await Promise.all([getSettings(), getBooks()])
  newPerDay.value = s.new_per_day
  reviewPerDay.value = s.review_per_day
  activeBookId.value = s.active_book_id
  books.value = b
}

onMounted(refreshAll)

async function save() {
  saving.value = true
  try {
    await updateSettings({
      new_per_day: newPerDay.value,
      review_per_day: reviewPerDay.value,
      active_book_id: activeBookId.value ?? undefined,
    })
    ElMessage.success('设置已保存，立即生效')
  } finally {
    saving.value = false
  }
}

async function savePassword() {
  if (!passwordForm.current) {
    ElMessage.warning('请输入当前密码')
    return
  }
  if (passwordForm.next.length < 8 || passwordForm.next.length > 128) {
    ElMessage.warning('新密码长度需为 8–128 个字符')
    return
  }
  if (passwordForm.next !== passwordForm.confirm) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  passwordSaving.value = true
  try {
    await changePassword(passwordForm.current, passwordForm.next)
    ElMessage.success('密码已修改，请使用新密码重新登录')
    auth.clear()
    router.replace('/login')
  } finally {
    passwordSaving.value = false
  }
}

async function onExport() {
  exportLoading.value = true
  try {
    const blob = await exportBackup()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `vocab-assistant-backup-${new Date().toISOString().slice(0, 10)}.json`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    ElMessage.success('备份已导出')
  } finally {
    exportLoading.value = false
  }
}

function pickImportFile() {
  importInput.value?.click()
}

async function onImportFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  importLoading.value = true
  try {
    const result = await importBackup(file)
    const skipped = result.skipped ? `，跳过 ${result.skipped} 项` : ''
    ElMessage.success(
      `导入完成：${result.books_imported} 本词书、${result.words_imported} 个单词${skipped}`,
    )
    await refreshAll()
  } finally {
    importLoading.value = false
  }
}
</script>

<template>
  <div class="page">
    <h1 class="page-title">设置</h1>

    <el-card shadow="never" class="section-card">
      <template #header>每日任务量（新词 : 复习 = 1 : 2）</template>
      <div class="tier-grid">
        <div
          v-for="t in TIERS"
          :key="t.label"
          class="tier-card"
          :class="{ active: matchedTier?.label === t.label }"
          @click="applyTier(t)"
        >
          <div class="tier-label">{{ t.label }}</div>
          <div class="tier-nums">新 {{ t.new }} / 复 {{ t.review }}</div>
          <div class="tier-desc text-muted">{{ t.desc }}</div>
        </div>
      </div>

      <el-divider />

      <div class="slider-row">
        <div class="slider-item">
          <span class="slider-label">每日新词：{{ newPerDay }} 个</span>
          <el-slider
            v-model="newPerDay"
            :min="10"
            :max="250"
            :step="5"
            show-stops
            :marks="{ 25: '25', 100: '100', 200: '200' }"
          />
        </div>
        <div class="slider-item">
          <span class="slider-label">每日复习：{{ reviewPerDay }} 个</span>
          <el-slider
            v-model="reviewPerDay"
            :min="20"
            :max="500"
            :step="10"
            show-stops
            :marks="{ 50: '50', 200: '200', 400: '400' }"
          />
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>当前词书</template>
      <el-select
        v-model="activeBookId"
        placeholder="选择要学习的词书"
        style="width: 360px"
        size="large"
        clearable
      >
        <el-option
          v-for="b in books"
          :key="b.id"
          :label="`${b.name}（${b.word_count} 词）`"
          :value="b.id"
        />
      </el-select>
      <div v-if="!books.length" class="text-muted" style="margin-top: 8px">
        还没有词书，请先到「词书管理」上传
      </div>
    </el-card>

    <el-button type="primary" size="large" class="save-btn" :loading="saving" @click="save"
      >保存设置</el-button
    >

    <el-card shadow="never" class="section-card security-card">
      <template #header>账号安全</template>
      <div class="form-grid">
        <el-input
          v-model="passwordForm.current"
          type="password"
          show-password
          autocomplete="current-password"
          placeholder="当前密码"
        />
        <el-input
          v-model="passwordForm.next"
          type="password"
          show-password
          autocomplete="new-password"
          placeholder="新密码（8–128 个字符）"
        />
        <el-input
          v-model="passwordForm.confirm"
          type="password"
          show-password
          autocomplete="new-password"
          placeholder="再次输入新密码"
        />
      </div>
      <el-button type="primary" plain :loading="passwordSaving" @click="savePassword">
        修改密码
      </el-button>
      <p class="hint text-muted">修改成功后，其他设备上的登录会立即失效。</p>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>数据备份</template>
      <p class="hint text-muted">
        备份包含词书、记忆状态与学习流水，文件为 JSON。请妥善保管，不要上传到公开位置。
      </p>
      <div class="backup-actions">
        <el-button :loading="exportLoading" @click="onExport">导出备份</el-button>
        <el-button :loading="importLoading" @click="pickImportFile">导入备份（合并）</el-button>
        <input
          ref="importInput"
          type="file"
          accept=".json,application/json"
          class="hidden-input"
          @change="onImportFile"
        />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.section-card {
  margin-bottom: 18px;
}

.tier-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 12px;
}
.tier-card {
  border: 2px solid #e4e7ed;
  border-radius: 10px;
  padding: 14px 6px;
  text-align: center;
  cursor: pointer;
  transition: all 0.15s;
}
.tier-card:hover {
  border-color: #a0cfff;
}
.tier-card.active {
  border-color: #409eff;
  background: #ecf5ff;
}
.tier-label {
  font-size: 16px;
  font-weight: 700;
  color: #303133;
}
.tier-nums {
  font-size: 13px;
  color: #409eff;
  margin-top: 6px;
  font-weight: 600;
}
.tier-desc {
  font-size: 12px;
  margin-top: 4px;
}

.slider-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.slider-item {
  padding: 0 12px;
}
.slider-label {
  font-size: 14px;
  color: #606266;
}

.save-btn {
  padding: 20px 44px;
  font-size: 15px;
  border-radius: 22px;
  margin-bottom: 18px;
}

.security-card {
  margin-top: 8px;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}
.hint {
  font-size: 13px;
  line-height: 1.6;
  margin: 10px 0;
}
.backup-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.hidden-input {
  display: none;
}

@media (max-width: 640px) {
  .section-card :deep(.el-select) {
    width: 100% !important;
  }
  .save-btn {
    width: 100%;
  }
}
</style>
