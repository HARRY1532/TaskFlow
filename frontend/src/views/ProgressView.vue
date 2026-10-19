<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { progressApi } from '../api/progress'
import { projectApi } from '../api/project'
import { taskApi } from '../api/task'
import { useAuthStore } from '../stores/auth'
import { formatBeijingTime } from '../utils/date'
import type { ProgressReport, ProgressSnapshot, Project, Task } from '../types'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const projectId = Number(route.params.id)
const project = ref<Project | null>(null)
const snapshot = ref<ProgressSnapshot | null>(null)
const reports = ref<ProgressReport[]>([])
const report = ref<ProgressReport | null>(null)
const tasks = ref<Task[]>([])
const generating = ref(false)
const taskTitle = (id: number) => tasks.value.find(task => task.id === id)?.title || `任务 ${id}`
const severityType = (severity: string) => severity === 'high' ? 'error' : severity === 'medium' ? 'warning' : 'info'

async function load() {
  try {
    project.value = await projectApi.get(projectId)
    if (project.value.owner_id !== auth.user?.id) {
      ElMessage.error('只有项目负责人可以查看进度诊断')
      await router.replace(`/projects/${projectId}`)
      return
    }
    const [current, history, taskRows] = await Promise.all([
      progressApi.snapshot(projectId), progressApi.reports(projectId), taskApi.list(projectId),
    ])
    snapshot.value = current
    reports.value = history
    report.value = history[0] || null
    tasks.value = taskRows
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载进度诊断失败') }
}

async function generate() {
  generating.value = true
  try {
    const result = await progressApi.generate(projectId)
    reports.value.unshift(result)
    report.value = result
    snapshot.value = result.snapshot
    ElMessage.success('进度报告已生成')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '生成报告失败') }
  finally { generating.value = false }
}

onMounted(load)
</script>

<template>
  <div v-if="project">
    <div class="page-header">
      <div><router-link :to="`/projects/${projectId}`">← 返回项目看板</router-link><h1>项目进度诊断</h1><p>风险来自当前任务数据，AI 给出调整建议；报告不会修改任务。</p></div>
      <el-button type="primary" :loading="generating" :disabled="!snapshot?.total_tasks" @click="generate">生成 AI 报告</el-button>
    </div>
    <template v-if="snapshot">
      <el-card style="margin-bottom: 18px">
        <strong>当前进度 · {{ snapshot.as_of }}（北京时间）</strong>
        <p>已完成 {{ snapshot.completed_tasks }} / {{ snapshot.total_tasks }} 项任务</p>
        <el-progress :percentage="snapshot.completion_rate" />
        <el-space wrap style="margin-top: 14px">
          <el-tag>待开始 {{ snapshot.status_counts.todo || 0 }}</el-tag>
          <el-tag type="primary">进行中 {{ snapshot.status_counts.in_progress || 0 }}</el-tag>
          <el-tag type="warning">待验收 {{ snapshot.status_counts.review || 0 }}</el-tag>
          <el-tag type="success">已完成 {{ snapshot.status_counts.done || 0 }}</el-tag>
        </el-space>
      </el-card>
      <el-card style="margin-bottom: 18px">
        <h3>当前风险</h3>
        <el-empty v-if="!snapshot.findings.length" description="目前未发现规则定义的进度风险" />
        <el-alert v-for="(finding, index) in snapshot.findings" :key="index" :title="finding.title" :description="finding.detail" :type="severityType(finding.severity)" :closable="false" style="margin-bottom: 10px" />
      </el-card>
      <el-card style="margin-bottom: 18px">
        <h3>成员未完成任务分布</h3>
        <el-table :data="snapshot.workload" style="width: 100%">
          <el-table-column prop="member_name" label="成员" />
          <el-table-column prop="open_task_count" label="任务数" />
          <el-table-column prop="estimated_hours" label="预计总工时" />
        </el-table>
        <p class="muted">预计总工时仅汇总任务卡片已填写的工时，不能直接视为本周工时。</p>
      </el-card>
    </template>
    <el-card v-if="reports.length" style="margin-bottom: 20px">
      <h3>AI 报告记录</h3>
      <el-select :model-value="report?.id" style="width: 240px; max-width: 100%" @change="(id: number) => report = reports.find(item => item.id === id) || null">
        <el-option v-for="item in reports" :key="item.id" :value="item.id" :label="formatBeijingTime(item.created_at)" />
      </el-select>
      <template v-if="report">
        <p class="muted">报告生成于 {{ formatBeijingTime(report.created_at) }}（北京时间）；当时完成率 {{ report.snapshot.completion_rate }}%</p>
        <p>{{ report.diagnosis.summary }}</p>
        <el-empty v-if="!report.diagnosis.actions.length" description="暂无调整建议" />
        <div v-for="(action, index) in report.diagnosis.actions" :key="index" style="padding: 12px 0; border-top: 1px solid var(--el-border-color-lighter)">
          <strong>{{ action.title }}</strong>
          <p>{{ action.detail }}</p>
          <p v-if="action.related_task_ids.length" class="muted">相关任务：{{ action.related_task_ids.map(taskTitle).join('、') }}</p>
        </div>
      </template>
    </el-card>
  </div>
</template>
