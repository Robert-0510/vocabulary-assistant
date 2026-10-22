<script setup lang="ts">
import { onBeforeUnmount, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import QuizCard from '@/components/QuizCard.vue'
import PronounceButton from '@/components/PronounceButton.vue'
import WordDetailCard from '@/components/WordDetailCard.vue'
import { useStudyStore } from '@/stores/study'
import { pronounce } from '@/utils/speech'

const store = useStudyStore()
const router = useRouter()

onMounted(() => {
  store.loadToday()
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

watch(
  () => store.current,
  (item) => {
    // 新词首见自动读一遍
    if (item && item.step === 'intro') {
      setTimeout(() => pronounce(item.word.spelling), 200)
    }
  },
)

function onKey(e: KeyboardEvent) {
  const item = store.current
  if (store.loading || store.finished || !item) return
  if (e.code === 'Space') {
    e.preventDefault()
    pronounce(item.word.spelling)
    return
  }
  if (item.step === 'intro') {
    if (e.key === '1') store.answerIntro('know')
    else if (e.key === '2') store.answerIntro('unknown')
    else if (e.key === '3') store.answerIntro('master')
  } else if (item.step === 'detail') {
    if (e.key === 'Enter' || e.key === '1') store.continueNext()
  }
  // quiz / recheck 步骤的按键由 QuizCard 内部处理（1-4 选答案）
}

const quizLabel = () => {
  const item = store.current
  if (!item) return ''
  if (item.step === 'recheck') return '快速复查'
  return item.kind === 'new' ? '新词测试' : '复习测试'
}
</script>

<template>
  <div class="page study-page">
    <!-- 加载中 -->
    <div
      v-if="store.loading"
      v-loading="true"
      class="study-card loading-card"
      element-loading-text="正在生成今日任务…"
    />

    <!-- 未选择词书 -->
    <div v-else-if="store.noBook" class="study-card">
      <el-empty description="还没有选择词书，先去上传一本吧">
        <el-button type="primary" size="large" @click="router.push('/books')">去上传词书</el-button>
      </el-empty>
    </div>

    <!-- 加载失败：区分于「今日已完成」 -->
    <div v-else-if="store.error" class="study-card">
      <el-empty description="今日任务加载失败，请检查后端服务是否正常">
        <el-button type="primary" size="large" @click="store.loadToday()">重试</el-button>
        <el-button @click="router.push('/')">返回首页</el-button>
      </el-empty>
    </div>

    <!-- 今日无任务 -->
    <div v-else-if="store.emptyToday" class="study-card">
      <el-empty description="今日没有待学习的任务，词书可能已全部学完 🎉">
        <el-button type="primary" plain @click="router.push('/stats')">查看统计</el-button>
        <el-button @click="router.push('/')">返回首页</el-button>
      </el-empty>
    </div>

    <!-- 全部完成 -->
    <div v-else-if="store.finished" class="study-card done-card">
      <div class="done-emoji">🎉</div>
      <h2>今日任务完成！</h2>
      <p class="done-summary">
        新学 <b>{{ store.newDone }}</b> 个单词 · 复习 <b>{{ store.reviewDone }}</b> 个单词
      </p>
      <div class="done-btns">
        <el-button type="primary" size="large" @click="router.push('/stats')">查看统计</el-button>
        <el-button size="large" @click="router.push('/')">返回首页</el-button>
      </div>
    </div>

    <!-- 学习中 -->
    <template v-else-if="store.current">
      <div class="progress-row">
        <el-progress
          :percentage="store.progressPct"
          :stroke-width="14"
          :format="(p: number) => `${p}%`"
        />
        <div class="counters" aria-live="polite">
          新词 {{ store.newDone }}/{{ store.newTarget || store.newDone }} · 复习
          {{ store.reviewDone }}/{{ store.reviewTarget || store.reviewDone }} · 进度
          {{ store.graduated }}/{{ store.totalGraduate }}
        </div>
        <el-button text type="info" @click="router.push('/')">结束学习</el-button>
      </div>

      <div class="study-card card-area" :aria-busy="store.busy">
        <!-- 新词首见：自评 -->
        <div v-if="store.current.step === 'intro'" class="intro">
          <div class="kind-tag">
            <el-tag :type="store.current.kind === 'new' ? 'success' : 'primary'" effect="dark">
              {{ store.current.kind === 'new' ? '新词' : '复习' }}
            </el-tag>
          </div>
          <h1 class="spelling">{{ store.current.word.spelling }}</h1>
          <div class="phonetic-row">
            <span v-if="store.current.word.phonetic" class="phonetic">{{
              store.current.word.phonetic
            }}</span>
            <PronounceButton :word="store.current.word.spelling" size="large" />
          </div>
          <p class="ask">你还记得它的意思吗？</p>
          <div class="btn-row">
            <el-button type="success" size="large" @click="store.answerIntro('know')">
              认识 <span class="kbd-hint">1</span>
            </el-button>
            <el-button type="danger" size="large" @click="store.answerIntro('unknown')">
              不认识 <span class="kbd-hint">2</span>
            </el-button>
            <el-button type="primary" size="large" @click="store.answerIntro('master')">
              熟知 <span class="kbd-hint">3</span>
            </el-button>
          </div>
        </div>

        <!-- 详情卡：释义 + 例句 -->
        <div v-else-if="store.current.step === 'detail'" class="detail">
          <WordDetailCard :key="store.current.key" :word="store.current.word" />
          <el-button type="primary" size="large" class="detail-next" @click="store.continueNext()">
            我记住了，继续 <span class="kbd-hint">回车</span>
          </el-button>
        </div>

        <!-- 测试卡 -->
        <QuizCard
          v-else
          :key="store.current.key + '-' + store.current.step"
          :word="store.current.word"
          :quiz="store.current.word.quiz!"
          :label="quizLabel()"
          @answered="store.answerQuiz"
          @next="store.continueNext"
        />
      </div>

      <div class="kbd-tips text-muted">
        <span class="kbd-hint">空格</span>发音
        <template v-if="store.current.step === 'intro'">
          · <span class="kbd-hint">1</span>认识 · <span class="kbd-hint">2</span>不认识 ·
          <span class="kbd-hint">3</span>熟知
        </template>
        <template v-else-if="store.current.step === 'detail'">
          · <span class="kbd-hint">回车</span>继续
        </template>
        <template v-else> · <span class="kbd-hint">1-4</span>选择答案 </template>
      </div>
    </template>
  </div>
</template>

<style scoped>
.study-page {
  max-width: 760px;
}

.progress-row {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 14px;
}
.progress-row .el-progress {
  flex: 1;
}
.counters {
  white-space: nowrap;
  font-size: 13px;
  color: #606266;
}

.study-card {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  padding: 34px 30px;
  min-height: 460px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.loading-card {
  align-items: center;
}

.card-area :deep(.el-button + .el-button) {
  margin-left: 0;
}

/* 新词自评 */
.intro,
.detail {
  text-align: center;
}
.kind-tag {
  margin-bottom: 10px;
}
.spelling {
  margin: 0;
  font-size: 52px;
  font-weight: 700;
  color: #303133;
  letter-spacing: 1px;
}
.phonetic-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 10px;
}
.phonetic {
  color: #909399;
  font-size: 17px;
}
.ask {
  color: #909399;
  margin: 22px 0 18px;
  font-size: 15px;
}
.btn-row {
  display: flex;
  justify-content: center;
  gap: 16px;
}
.btn-row .el-button {
  padding: 22px 26px;
  font-size: 16px;
}
.btn-row .el-button + .el-button {
  margin-left: 16px;
}

.detail-next {
  margin-top: 24px;
}

/* 完成页 */
.done-card {
  text-align: center;
}
.done-emoji {
  font-size: 64px;
}
.done-summary {
  color: #606266;
  font-size: 16px;
}
.done-btns {
  margin-top: 22px;
}

.kbd-tips {
  text-align: center;
  margin-top: 14px;
  font-size: 13px;
}

@media (max-width: 900px) {
  .progress-row {
    flex-wrap: wrap;
  }
  .counters {
    white-space: normal;
  }
}

@media (max-width: 640px) {
  .study-card {
    padding: 22px 16px;
    min-height: 400px;
  }
  .spelling {
    font-size: clamp(34px, 11vw, 48px);
  }
  .btn-row {
    flex-wrap: wrap;
    gap: 10px;
  }
  .btn-row .el-button {
    flex: 1 1 140px;
    margin-left: 0 !important;
  }
  .detail-next {
    width: 100%;
  }
  .kbd-tips {
    line-height: 1.9;
  }
}
</style>
