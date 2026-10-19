<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import AnalyticsChart from '../components/AnalyticsChart.vue'
import { analyticsApi } from '../api/analytics'
import { projectApi } from '../api/project'
import type { Project, ProjectAnalytics } from '../types'

const route = useRoute()
const projectId = Number(route.params.id)
const project = ref<Project | null>(null)
const analytics = ref<ProjectAnalytics | null>(null)
const loading = ref(false)
const statusNames: Record<string, string> = {
  todo: '待开始', in_progress: '进行中', review: '待验收', done: '已完成',
}
const statuses = ['todo', 'in_progress', 'review', 'done']
const colors = ['#94a3b8', '#3b82f6', '#f59e0b', '#10b981']

const statusOption = computed(() => ({
  color: colors,
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  series: [{ type: 'pie', radius: ['44%', '69%'], center: ['50%', '43%'],
    label: { formatter: '{b}：{c}' },
    data: statuses.map(status => ({ name: statusNames[status], value: analytics.value?.status_counts[status] || 0 })),
  }],
}))
const memberOption = computed(() => ({
  color: colors,
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  legend: { bottom: 0 },
  grid: { left: 42, right: 20, top: 24, bottom: 66, containLabel: true },
  xAxis: { type: 'category', data: analytics.value?.members.map(member => member.member_name) || [],
    axisLabel: { interval: 0, rotate: 25 } },
  yAxis: { type: 'value', minInterval: 1, name: '任务数' },
  series: statuses.map(status => ({ name: statusNames[status], type: 'bar', stack: 'total',
    data: analytics.value?.members.map(member => member.status_counts[status] || 0) || [] })),
}))
const hoursOption = computed(() => ({
  color: ['#6366f1'],
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  grid: { left: 42, right: 20, top: 24, bottom: 55, containLabel: true },
  xAxis: { type: 'category', data: analytics.value?.members.map(member => member.member_name) || [],
    axisLabel: { interval: 0, rotate: 25 } },
  yAxis: { type: 'value', name: '小时' },
  series: [{ name: '预计总工时', type: 'bar', barMaxWidth: 44,
    data: analytics.value?.members.map(member => member.estimated_hours) || [] }],
}))
const weightOption = computed(() => ({
  color: ['#8b5cf6'],
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  grid: { left: 48, right: 20, top: 24, bottom: 85, containLabel: true },
  xAxis: { type: 'category', data: analytics.value?.weights.map(weight => weight.task_title) || [],
    axisLabel: { interval: 0, rotate: 30, width: 90, overflow: 'truncate' } },
  yAxis: { type: 'value', min: 0, max: 100, name: '规划分值' },
  dataZoom: analytics.value && analytics.value.weights.length > 8
    ? [{ type: 'slider', xAxisIndex: 0, start: 0, end: Math.round(800 / analytics.value.weights.length) }]
    : [],
  series: [{ name: '已确认权重', type: 'bar', barMaxWidth: 42,
    data: analytics.value?.weights.map(weight => weight.confirmed_score) || [] }],
}))
const trendOption = computed(() => ({
  color: ['#3b82f6', '#10b981'],
  tooltip: { trigger: 'axis' },
  legend: { bottom: 0 },
  grid: { left: 42, right: 20, top: 24, bottom: 62, containLabel: true },
  xAxis: { type: 'category', boundaryGap: false,
    data: analytics.value?.trend.map(point => point.date.slice(5)) || [] },
  yAxis: { type: 'value', minInterval: 1, name: '任务数' },
  series: [
    { name: '已有任务', type: 'line', smooth: true, data: analytics.value?.trend.map(point => point.total_tasks) || [] },
    { name: '已完成', type: 'line', smooth: true, areaStyle: { opacity: 0.12 },
      data: analytics.value?.trend.map(point => point.completed_tasks) || [] },
  ],
}))

async function load() {
  loading.value = true
  try {
    const [projectData, analyticsData] = await Promise.all([
      projectApi.get(projectId), analyticsApi.get(projectId),
    ])
    project.value = projectData
    analytics.value = analyticsData
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载数据分析失败') }
  finally { loading.value = false }
}

onMounted(load)
</script>

<template>
  <div v-if="project" class="analytics-page">
    <div class="page-header">
      <div><router-link :to="`/projects/${projectId}`">← 返回项目看板</router-link><h1>项目数据分析</h1><p>按当前项目任务和历史事件汇总，所有项目成员可查看。</p></div>
      <el-button :loading="loading" @click="load">刷新数据</el-button>
    </div>
    <template v-if="analytics">
      <el-row :gutter="16" style="margin-bottom: 18px">
        <el-col :xs="24" :sm="8"><el-card><div class="metric-label">任务总数</div><div class="metric-value">{{ analytics.total_tasks }}</div></el-card></el-col>
        <el-col :xs="24" :sm="8"><el-card><div class="metric-label">已完成</div><div class="metric-value">{{ analytics.completed_tasks }}</div></el-card></el-col>
        <el-col :xs="24" :sm="8"><el-card><div class="metric-label">完成率</div><div class="metric-value">{{ analytics.completion_rate }}%</div></el-card></el-col>
      </el-row>
      <el-empty v-if="!analytics.total_tasks" description="项目还没有任务，创建任务后即可查看图表" />
      <template v-else>
        <div class="chart-grid">
          <el-card><h3>任务状态分布</h3><AnalyticsChart :option="statusOption" /></el-card>
          <el-card><h3>成员任务状态</h3><AnalyticsChart :option="memberOption" /></el-card>
          <el-card><h3>成员预计工时</h3><AnalyticsChart :option="hoursOption" /></el-card>
          <el-card><h3>已确认任务权重</h3>
            <AnalyticsChart v-if="analytics.weights.length" :option="weightOption" />
            <el-empty v-else description="暂无已确认的任务权重" />
          </el-card>
        </div>
        <el-card style="margin-top: 18px"><h3>近 14 天任务完成趋势</h3><AnalyticsChart :option="trendOption" :height="340" />
          <p class="muted">趋势根据目前仍存在的任务及其创建、验收事件计算。删除任务后，其事件也会删除；此图不代表完整历史审计记录。预计工时是任务总估计，不是本周工时。</p>
        </el-card>
        <el-card style="margin-top: 18px"><h3>任务截止日期安排</h3>
          <el-table v-if="analytics.schedule.length" :data="analytics.schedule" style="width: 100%">
            <el-table-column prop="task_title" label="任务" min-width="180" />
            <el-table-column prop="due_date" label="截止日期" width="130" />
            <el-table-column label="状态" width="110"><template #default="scope">{{ statusNames[scope.row.status] || scope.row.status }}</template></el-table-column>
            <el-table-column prop="assignee_name" label="任务执行人" min-width="130"><template #default="scope">{{ scope.row.assignee_name || '未分配' }}</template></el-table-column>
          </el-table>
          <el-empty v-else description="暂无设置截止日期的任务" />
        </el-card>
      </template>
    </template>
  </div>
</template>

<style scoped>
.chart-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.chart-grid h3 { margin: 0 0 8px; font-size: 17px; }
.metric-label { color: #718096; font-size: 14px; }
.metric-value { color: #1e3a5f; font-size: 30px; font-weight: 700; margin-top: 8px; }
@media (max-width: 760px) { .chart-grid { grid-template-columns: 1fr; } }
</style>
