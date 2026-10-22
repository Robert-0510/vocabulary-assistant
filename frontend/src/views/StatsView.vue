<script setup lang="ts">
import { BarChart, HeatmapChart, PieChart } from 'echarts/charts'
import {
  AxisPointerComponent,
  CalendarComponent,
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components'
import * as echarts from 'echarts/core'
import type { ECharts } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { getCalendar, getRecent, getStatsOverview } from '@/api'
import type { StatsOverview } from '@/api/types'

echarts.use([
  BarChart,
  HeatmapChart,
  PieChart,
  AxisPointerComponent,
  CalendarComponent,
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
])

const overview = ref<StatsOverview | null>(null)

const pieEl = ref<HTMLElement>()
const barEl = ref<HTMLElement>()
const heatEl = ref<HTMLElement>()
let pieChart: ECharts | null = null
let barChart: ECharts | null = null
let heatChart: ECharts | null = null

function monthStr(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

/** 相对当前月份偏移 n 个月的 1 号（避免 31 号 setMonth 溢出）。 */
function monthStartOffset(n: number): Date {
  const now = new Date()
  return new Date(now.getFullYear(), now.getMonth() - n, 1)
}

async function loadCharts() {
  const [recent, c1, c2, c3] = await Promise.all([
    getRecent(30),
    getCalendar(monthStr(monthStartOffset(0))),
    getCalendar(monthStr(monthStartOffset(1))),
    getCalendar(monthStr(monthStartOffset(2))),
  ])

  // 状态分布饼图
  if (pieEl.value) {
    pieChart = echarts.init(pieEl.value)
    pieChart.setOption({
      title: { text: '记忆状态分布', left: 'center' },
      tooltip: { trigger: 'item' },
      series: [
        {
          type: 'pie',
          radius: ['38%', '64%'],
          center: ['50%', '54%'],
          label: { formatter: '{b}: {c}' },
          data: [
            { name: '新词', value: overview.value?.new ?? 0, itemStyle: { color: '#909399' } },
            {
              name: '学习中',
              value: overview.value?.learning ?? 0,
              itemStyle: { color: '#e6a23c' },
            },
            {
              name: '复习中',
              value: overview.value?.reviewing ?? 0,
              itemStyle: { color: '#409eff' },
            },
            {
              name: '已掌握',
              value: overview.value?.mastered ?? 0,
              itemStyle: { color: '#67c23a' },
            },
          ],
        },
      ],
    })
  }

  // 近 30 天柱状图
  if (barEl.value) {
    barChart = echarts.init(barEl.value)
    barChart.setOption({
      title: { text: '近 30 天学习量', left: 'center' },
      tooltip: { trigger: 'axis' },
      legend: { data: ['新词', '复习'], top: 26 },
      grid: { left: 40, right: 16, top: 62, bottom: 26 },
      xAxis: {
        type: 'category',
        data: recent.map((d) => d.date.slice(5)),
        axisLabel: { interval: 4 },
      },
      yAxis: { type: 'value' },
      series: [
        {
          name: '新词',
          type: 'bar',
          stack: 'total',
          barMaxWidth: 26,
          color: '#409eff',
          data: recent.map((d) => d.new_count),
        },
        {
          name: '复习',
          type: 'bar',
          stack: 'total',
          barMaxWidth: 26,
          color: '#e6a23c',
          data: recent.map((d) => d.review_count),
        },
      ],
    })
  }

  // 打卡热力图（近 3 个月）
  if (heatEl.value) {
    const all = [...c3, ...c2, ...c1]
    const start = monthStartOffset(2)
    heatChart = echarts.init(heatEl.value)
    heatChart.setOption({
      title: { text: '打卡热力图', left: 'center' },
      tooltip: {
        formatter: (p: { data: [string, number] }) => `${p.data[0]}：学习 ${p.data[1]} 词`,
      },
      visualMap: {
        min: 0,
        max: Math.max(10, ...all.map((d) => d.count)),
        calculable: false,
        orient: 'horizontal',
        left: 'center',
        bottom: 0,
        inRange: { color: ['#f0f2f5', '#a0cfff', '#409eff', '#1d6fd0'] },
      },
      calendar: {
        range: [start, new Date()],
        cellSize: ['auto', 16],
        left: 40,
        right: 16,
        top: 60,
        itemStyle: { borderWidth: 2, borderColor: '#fff' },
        yearLabel: { show: false },
        monthLabel: { nameMap: 'ZH' },
        dayLabel: { nameMap: 'ZH', firstDay: 1 },
        splitLine: { show: false },
      },
      series: [
        {
          type: 'heatmap',
          coordinateSystem: 'calendar',
          data: all.map((d) => [d.date, d.count]),
        },
      ],
    })
  }
}

function onResize() {
  pieChart?.resize()
  barChart?.resize()
  heatChart?.resize()
}

onMounted(async () => {
  overview.value = await getStatsOverview()
  await loadCharts()
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  pieChart?.dispose()
  barChart?.dispose()
  heatChart?.dispose()
})
</script>

<template>
  <div class="page">
    <h1 class="page-title">学习统计</h1>

    <el-row :gutter="16" class="overview-row">
      <el-col :span="6" :xs="12" :sm="6"
        ><el-card shadow="hover"
          ><el-statistic title="总词数" :value="overview?.total_words ?? 0" /></el-card
      ></el-col>
      <el-col :span="6" :xs="12" :sm="6"
        ><el-card shadow="hover"
          ><el-statistic title="已掌握" :value="overview?.mastered ?? 0" /></el-card
      ></el-col>
      <el-col :span="6" :xs="12" :sm="6"
        ><el-card shadow="hover"
          ><el-statistic title="累计学习天数" :value="overview?.total_days ?? 0" /></el-card
      ></el-col>
      <el-col :span="6" :xs="12" :sm="6"
        ><el-card shadow="hover"
          ><el-statistic title="连续打卡" :value="overview?.streak_days ?? 0" /></el-card
      ></el-col>
    </el-row>

    <el-row :gutter="16" class="chart-row">
      <el-col :span="10" :xs="24" :sm="10">
        <el-card shadow="hover"><div ref="pieEl" class="chart chart-pie" /></el-card>
      </el-col>
      <el-col :span="14" :xs="24" :sm="14">
        <el-card shadow="hover"><div ref="barEl" class="chart" /></el-card>
      </el-col>
    </el-row>

    <el-card shadow="hover" class="heat-card">
      <div ref="heatEl" class="chart chart-heat" />
    </el-card>
  </div>
</template>

<style scoped>
.overview-row {
  margin-bottom: 16px;
}
.chart {
  height: 340px;
  width: 100%;
}
.chart-pie {
  height: 340px;
}
.chart-heat {
  height: 230px;
}
.heat-card {
  margin-top: 16px;
}

@media (max-width: 900px) {
  .overview-row > .el-col {
    margin-bottom: 12px;
  }
  .chart-row > .el-col {
    margin-bottom: 12px;
  }
  .chart,
  .chart-pie {
    height: 280px;
  }
  .chart-heat {
    height: 220px;
  }
}
</style>
