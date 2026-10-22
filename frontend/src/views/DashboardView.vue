<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getCalendar, getProgress, getStatsOverview } from '@/api'
import type { CalendarDay, Progress, StatsOverview } from '@/api/types'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const overview = ref<StatsOverview | null>(null)
const progress = ref<Progress | null>(null)
const countByDate = ref<Record<string, number>>({})
const calendarDate = ref(new Date())
const loadedMonth = ref('')

function monthStr(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

async function loadCalendar(month: string) {
  const days: CalendarDay[] = await getCalendar(month)
  countByDate.value = Object.fromEntries(days.map((d) => [d.date, d.count]))
}

/** 翻月时重新拉取；点击具体日期不会重复请求同一个月。 */
function syncCalendar(d: Date) {
  const month = monthStr(d)
  if (month === loadedMonth.value) return
  loadedMonth.value = month
  loadCalendar(month)
}

// Element Plus 的 el-calendar 没有 panel-change 事件，只能监听 v-model。
watch(calendarDate, syncCalendar)

onMounted(async () => {
  if (!auth.user) return
  const [ov, pg] = await Promise.all([getStatsOverview(), getProgress().catch(() => null)])
  overview.value = ov
  progress.value = pg
  syncCalendar(calendarDate.value)
})

function pct(done: number, target: number): number {
  if (!target) return 100
  return Math.min(100, Math.round((done / target) * 100))
}
</script>

<template>
  <!-- 未登录：只展示登录入口，不请求任何账号数据 -->
  <div v-if="!auth.user" class="page">
    <el-card class="welcome-card" shadow="never">
      <el-icon :size="58" color="#409eff"><Reading /></el-icon>
      <h2>登录后开始背单词</h2>
      <p class="text-muted">每个账号拥有独立的词书、记忆状态和学习统计，互不可见。</p>
      <el-button type="primary" size="large" class="welcome-btn" @click="router.push('/login')">
        登录 / 注册
      </el-button>
    </el-card>
  </div>

  <div v-else class="page">
    <h1 class="page-title">首页</h1>

    <el-row :gutter="16" class="stat-row">
      <el-col :span="8" :xs="24" :sm="8">
        <el-card shadow="hover">
          <el-statistic title="连续打卡（天）" :value="overview?.streak_days ?? 0">
            <template #suffix><span class="unit">天</span></template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="8" :xs="24" :sm="8">
        <el-card shadow="hover">
          <el-statistic title="今日已学（词）" :value="overview?.learned_today ?? 0" />
        </el-card>
      </el-col>
      <el-col :span="8" :xs="24" :sm="8">
        <el-card shadow="hover">
          <el-statistic title="已掌握 / 总词数" :value="overview?.mastered ?? 0">
            <template #suffix
              ><span class="unit">/ {{ overview?.total_words ?? 0 }}</span></template
            >
          </el-statistic>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="task-row">
      <el-col :span="14" :xs="24" :sm="14">
        <el-card shadow="hover" class="task-card">
          <div class="task-circles">
            <div class="circle-item">
              <el-progress
                type="dashboard"
                :percentage="pct(progress?.new_done ?? 0, progress?.new_target ?? 0)"
                :width="130"
              >
                <template #default>
                  <div class="circle-inner">
                    <div class="circle-num">
                      {{ progress?.new_done ?? 0 }}/{{ progress?.new_target ?? 0 }}
                    </div>
                    <div class="circle-label">今日新词</div>
                  </div>
                </template>
              </el-progress>
            </div>
            <div class="circle-item">
              <el-progress
                type="dashboard"
                :percentage="pct(progress?.review_done ?? 0, progress?.review_target ?? 0)"
                :width="130"
                color="#e6a23c"
              >
                <template #default>
                  <div class="circle-inner">
                    <div class="circle-num">
                      {{ progress?.review_done ?? 0 }}/{{ progress?.review_target ?? 0 }}
                    </div>
                    <div class="circle-label">今日复习</div>
                  </div>
                </template>
              </el-progress>
            </div>
          </div>
          <el-button type="primary" size="large" class="start-btn" @click="router.push('/study')">
            <el-icon><CaretRight /></el-icon>&nbsp;开始今日学习
          </el-button>
        </el-card>
      </el-col>
      <el-col :span="10" :xs="24" :sm="10">
        <el-card shadow="hover" class="calendar-card">
          <template #header>打卡日历</template>
          <el-calendar v-model="calendarDate">
            <template #date-cell="{ data }">
              <div class="cal-cell">
                <span>{{ data.day.split('-')[2] }}</span>
                <span v-if="countByDate[data.day]" class="cal-dot">{{
                  countByDate[data.day]
                }}</span>
              </div>
            </template>
          </el-calendar>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.welcome-card {
  max-width: 560px;
  margin: 10vh auto 0;
  border-radius: 16px;
  text-align: center;
  padding: 26px 20px;
}
.welcome-card h2 {
  margin: 14px 0 6px;
  color: #303133;
}
.welcome-card p {
  margin: 0 0 22px;
}
.welcome-btn {
  padding: 20px 46px;
  font-size: 16px;
  border-radius: 24px;
}

.stat-row {
  margin-bottom: 16px;
}
.unit {
  font-size: 14px;
  color: #909399;
  margin-left: 4px;
}

.task-row :deep(.el-card__body) {
  padding: 18px;
}
.task-card {
  height: 100%;
  text-align: center;
}
.task-circles {
  display: flex;
  justify-content: space-around;
  padding: 8px 0 18px;
}
.circle-inner {
  text-align: center;
}
.circle-num {
  font-size: 22px;
  font-weight: 700;
  color: #303133;
}
.circle-label {
  font-size: 13px;
  color: #909399;
  margin-top: 2px;
}
.start-btn {
  margin-top: 6px;
  font-size: 16px;
  padding: 20px 40px;
  border-radius: 24px;
}

.calendar-card :deep(.el-calendar) {
  --el-calendar-cell-width: 38px;
  background: transparent;
}
.calendar-card :deep(.el-calendar__header) {
  padding: 6px 0;
}
.calendar-card :deep(.el-calendar__body) {
  padding: 0;
}
.cal-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  font-size: 12px;
  height: 100%;
}
.cal-dot {
  margin-top: 1px;
  background: #409eff;
  color: #fff;
  border-radius: 8px;
  padding: 0 5px;
  font-size: 10px;
  line-height: 15px;
}

@media (max-width: 900px) {
  .stat-row > .el-col {
    margin-bottom: 12px;
  }
  .task-row > .el-col {
    margin-bottom: 12px;
  }
  .task-circles {
    flex-wrap: wrap;
    gap: 12px;
  }
  .calendar-card :deep(.el-calendar) {
    --el-calendar-cell-width: 34px;
  }
}

@media (max-width: 640px) {
  .task-circles {
    justify-content: center;
  }
  .start-btn {
    width: 100%;
  }
}
</style>
