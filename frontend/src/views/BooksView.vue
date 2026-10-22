<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadInstance, UploadRequestOptions } from 'element-plus'
import {
  activateBook,
  deleteBook,
  getBookWords,
  getBooks,
  resetBookProgress,
  updateWord,
  uploadBook,
} from '@/api'
import type { Book, WordPage } from '@/api/types'

const books = ref<Book[]>([])
const loading = ref(false)
const uploadRef = ref<UploadInstance>()

const STATUS_TAG: Record<
  string,
  { label: string; type: 'info' | 'warning' | 'primary' | 'success' }
> = {
  new: { label: '新词', type: 'info' },
  learning: { label: '学习中', type: 'warning' },
  reviewing: { label: '复习中', type: 'primary' },
  mastered: { label: '已掌握', type: 'success' },
}

async function refresh() {
  loading.value = true
  try {
    books.value = await getBooks()
  } finally {
    loading.value = false
  }
}
onMounted(refresh)

async function customUpload(options: UploadRequestOptions) {
  try {
    const res = await uploadBook(options.file)
    ElMessage.success(
      `《${res.name}》导入成功：${res.imported} 个单词${res.skipped ? `，跳过 ${res.skipped} 个重复/无效行` : ''}`,
    )
    await refresh()
  } catch {
    /* 错误提示已由拦截器弹出 */
  } finally {
    // 清空内部文件列表，否则 limit=1 会导致同一次页面会话只能上传一次
    uploadRef.value?.clearFiles()
  }
}

async function onActivate(book: Book) {
  await activateBook(book.id)
  ElMessage.success(`已切换当前词书：${book.name}`)
  refresh()
}

async function onDelete(book: Book) {
  try {
    await ElMessageBox.confirm(
      `删除词书《${book.name}》将同时删除其中 ${book.word_count} 个单词及全部学习进度，且不可恢复。`,
      '删除词书',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  await deleteBook(book.id)
  ElMessage.success('已删除')
  refresh()
}

async function onReset(book: Book) {
  try {
    await ElMessageBox.confirm(
      `将把《${book.name}》中的 ${book.word_count} 个单词全部恢复为新词，并删除这本书的学习流水。单词本身会保留，但进度不可恢复。`,
      '重置学习进度',
      { type: 'warning', confirmButtonText: '重置', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  await resetBookProgress(book.id)
  ElMessage.success('已重置该词书的进度')
  refresh()
}

// ---------- 单词纠错 ----------
const editVisible = ref(false)
const editSaving = ref(false)
const editingWord = reactive({
  id: 0,
  spelling: '',
  phonetic: '',
  definition: '',
  example_en: '',
  example_cn: '',
})

function openEdit(raw: unknown) {
  const row = raw as WordPage['items'][number]
  editingWord.id = row.id
  editingWord.spelling = row.spelling
  editingWord.phonetic = row.phonetic ?? ''
  editingWord.definition = row.definition
  editingWord.example_en = row.example_en ?? ''
  editingWord.example_cn = row.example_cn ?? ''
  editVisible.value = true
}

async function saveEdit() {
  if (!currentBook.value) return
  if (!editingWord.spelling.trim() || !editingWord.definition.trim()) {
    ElMessage.warning('单词与释义不能为空')
    return
  }
  editSaving.value = true
  try {
    await updateWord(currentBook.value.id, editingWord.id, {
      spelling: editingWord.spelling.trim(),
      phonetic: editingWord.phonetic,
      definition: editingWord.definition.trim(),
      example_en: editingWord.example_en || null,
      example_cn: editingWord.example_cn || null,
    })
    ElMessage.success('单词已更新')
    editVisible.value = false
    await loadWords()
    await refresh()
  } finally {
    editSaving.value = false
  }
}

// ---------- 词表弹窗 ----------
const dialogVisible = ref(false)
const currentBook = ref<Book | null>(null)
const wordPage = reactive<{ total: number; items: WordPage['items'] }>({ total: 0, items: [] })
const query = reactive({ page: 1, page_size: 20, keyword: '', status: '' })
const tableLoading = ref(false)

function openWords(book: Book) {
  currentBook.value = book
  query.page = 1
  query.keyword = ''
  query.status = ''
  dialogVisible.value = true
  loadWords()
}

function resetAndLoad() {
  query.page = 1
  loadWords()
}

async function loadWords() {
  if (!currentBook.value) return
  tableLoading.value = true
  try {
    const res = await getBookWords(currentBook.value.id, {
      page: query.page,
      page_size: query.page_size,
      keyword: query.keyword || undefined,
      status: query.status || undefined,
    })
    wordPage.total = res.total
    wordPage.items = res.items
  } finally {
    tableLoading.value = false
  }
}

function learnedPercent(b: Book): number {
  if (!b.word_count) return 0
  const learned = b.word_count - b.counts.new
  return Math.round((learned / b.word_count) * 100)
}
</script>

<template>
  <div class="page">
    <h1 class="page-title">词书管理</h1>

    <el-card shadow="never" class="upload-card">
      <el-upload
        ref="uploadRef"
        drag
        accept=".md,.markdown,.txt"
        :http-request="customUpload"
        :show-file-list="false"
        :limit="1"
      >
        <div class="upload-inner">
          <el-icon :size="44" color="#409eff"><UploadFilled /></el-icon>
          <div class="upload-text">将 .md 词书文件拖到此处，或 <em>点击上传</em></div>
          <div class="upload-tip">
            格式：| 单词 | 音标 | 释义 | 例句 |（例句可留空），参考 sample/示例词书.md
          </div>
        </div>
      </el-upload>
    </el-card>

    <div v-loading="loading" class="book-grid">
      <el-empty v-if="!loading && !books.length" description="还没有词书，先上传一本 .md 词书吧" />
      <el-card v-for="b in books" :key="b.id" shadow="hover" class="book-card">
        <div class="book-head">
          <span class="book-name">{{ b.name }}</span>
          <el-tag v-if="b.is_active" type="success" effect="dark" size="small">当前词书</el-tag>
        </div>
        <div class="book-meta text-muted">
          {{ b.word_count }} 词 · {{ new Date(b.created_at).toLocaleDateString() }}
        </div>
        <el-progress :percentage="learnedPercent(b)" :stroke-width="10" class="book-progress" />
        <div class="count-tags">
          <el-tag v-for="(v, s) in STATUS_TAG" :key="s" :type="v.type" effect="plain" size="small">
            {{ v.label }} {{ (b.counts as any)[s] }}
          </el-tag>
        </div>
        <div class="book-actions">
          <el-button size="small" @click="openWords(b)">词表</el-button>
          <el-button v-if="!b.is_active" size="small" type="primary" plain @click="onActivate(b)">
            设为当前
          </el-button>
          <el-button v-if="b.counts.new < b.word_count" size="small" plain @click="onReset(b)">
            重置进度
          </el-button>
          <el-button size="small" type="danger" plain @click="onDelete(b)">删除</el-button>
        </div>
      </el-card>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="`词表：${currentBook?.name ?? ''}`"
      width="min(860px, 94vw)"
      top="6vh"
    >
      <div class="filter-row">
        <el-input
          v-model="query.keyword"
          placeholder="搜索单词 / 释义"
          clearable
          style="width: 240px"
          @keyup.enter="resetAndLoad"
          @clear="resetAndLoad"
        >
          <template #prefix
            ><el-icon><Search /></el-icon
          ></template>
        </el-input>
        <el-select
          v-model="query.status"
          placeholder="全部状态"
          clearable
          style="width: 140px"
          @change="resetAndLoad"
        >
          <el-option v-for="(v, s) in STATUS_TAG" :key="s" :label="v.label" :value="s" />
        </el-select>
      </div>
      <el-table v-loading="tableLoading" :data="wordPage.items" height="480">
        <el-table-column prop="spelling" label="单词" width="150">
          <template #default="{ row }">
            <span class="table-word">{{ row.spelling }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="phonetic" label="音标" width="150" />
        <el-table-column prop="definition" label="释义" min-width="170" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="STATUS_TAG[row.status]?.type ?? 'info'" size="small" effect="plain">
              {{ STATUS_TAG[row.status]?.label ?? row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="间隔(天)" width="90" align="center">
          <template #default="{ row }">{{ row.interval_days }}</template>
        </el-table-column>
        <el-table-column label="到期日" width="110" align="center">
          <template #default="{ row }">{{ row.due_date ?? '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager-row">
        <el-pagination
          v-model:current-page="query.page"
          :page-size="query.page_size"
          :total="wordPage.total"
          layout="total, prev, pager, next"
          @current-change="loadWords"
        />
      </div>
    </el-dialog>

    <el-dialog v-model="editVisible" title="编辑单词" width="min(560px, 94vw)">
      <el-form label-width="72px" label-position="top">
        <el-form-item label="单词">
          <el-input v-model="editingWord.spelling" maxlength="100" />
        </el-form-item>
        <el-form-item label="音标">
          <el-input v-model="editingWord.phonetic" maxlength="200" />
        </el-form-item>
        <el-form-item label="释义">
          <el-input v-model="editingWord.definition" type="textarea" :rows="2" maxlength="1000" />
        </el-form-item>
        <el-form-item label="英文例句">
          <el-input v-model="editingWord.example_en" type="textarea" :rows="2" maxlength="2000" />
        </el-form-item>
        <el-form-item label="中文例句">
          <el-input v-model="editingWord.example_cn" maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="editSaving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.upload-card {
  margin-bottom: 18px;
}
.upload-card :deep(.el-upload-dragger) {
  padding: 26px 0;
}
.upload-inner {
  text-align: center;
}
.upload-text {
  color: #606266;
  font-size: 15px;
  margin-top: 8px;
}
.upload-text em {
  color: #409eff;
  font-style: normal;
}
.upload-tip {
  color: #909399;
  font-size: 12px;
  margin-top: 6px;
}

.book-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
  gap: 16px;
  min-height: 120px;
}
.book-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.book-name {
  font-size: 17px;
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.book-meta {
  font-size: 13px;
  margin: 6px 0 10px;
}
.book-progress {
  margin-bottom: 10px;
}
.count-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}
.book-actions {
  display: flex;
  gap: 0;
}

.filter-row {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}
.pager-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
.table-word {
  font-weight: 600;
}

@media (max-width: 900px) {
  .book-grid {
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  }
  .book-actions {
    flex-wrap: wrap;
    gap: 6px;
  }
  .filter-row {
    flex-wrap: wrap;
  }
  .filter-row :deep(.el-input) {
    width: 100% !important;
  }
  .filter-row :deep(.el-select) {
    width: 100% !important;
  }
}

@media (max-width: 640px) {
  .upload-tip {
    padding: 0 12px;
  }
  .pager-row {
    justify-content: center;
  }
}
</style>
