<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { assignmentApi } from '../api/assignments'
import { projectApi } from '../api/project'
import { taskApi } from '../api/task'
import { useAuthStore } from '../stores/auth'
import { formatBeijingTime } from '../utils/date'
import type { AssignmentDraft, Member, Project, Task } from '../types'

type EditableAssignment = {
  task_id: number; assignee_id: number; reason: string; risk_note: string; selected: boolean
}

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const projectId = Number(route.params.id)
const project = ref<Project | null>(null)
const members = ref<Member[]>([])
const tasks = ref<Task[]>([])
const drafts = ref<AssignmentDraft[]>([])
const draft = ref<AssignmentDraft | null>(null)
const rows = ref<EditableAssignment[]>([])
const generating = ref(false)
const confirming = ref(false)
const eligibleTasks = computed(() => tasks.value.filter(task => task.status === 'todo' && task.assignee_id === null))
const activeMembers = computed(() => members.value.filter(member => member.user.is_active))
const taskTitle = (id: number) => tasks.value.find(task => task.id === id)?.title || '任务已删除'
const memberName = (id: number) => members.value.find(member => member.user.id === id)?.user.name || '成员已退出'

function selectDraft(value: AssignmentDraft | null) {
  draft.value = value
  rows.value = value?.suggestion.recommendations.map(item => ({ ...item, selected: true })) || []
}

async function load() {
  try {
    project.value = await projectApi.get(projectId)
    if (project.value.owner_id !== auth.user?.id) {
      ElMessage.error('只有项目负责人可以使用智能分工')
      await router.replace(`/projects/${projectId}`)
      return
    }
    const [memberRows, taskRows, draftRows] = await Promise.all([
      projectApi.members(projectId), taskApi.list(projectId), assignmentApi.drafts(projectId),
    ])
    members.value = memberRows
    tasks.value = taskRows
    drafts.value = draftRows
    selectDraft(draftRows.find(item => item.status === 'pending') || null)
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载智能分工页面失败') }
}

async function generate() {
  generating.value = true
  try {
    const result = await assignmentApi.suggest(projectId)
    drafts.value.unshift(result)
    selectDraft(result)
    ElMessage.success('分工建议已生成，请审核')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '生成分工建议失败') }
  finally { generating.value = false }
}

async function confirm() {
  if (!draft.value) return
  const selected = rows.value.filter(row => row.selected).map(row => ({ task_id: row.task_id, assignee_id: row.assignee_id }))
  if (!selected.length) { ElMessage.error('请至少选择一项任务'); return }
  if (selected.some(row => !activeMembers.value.some(member => member.user.id === row.assignee_id))) {
    ElMessage.error('请选择有效的项目成员')
    return
  }
  try {
    await ElMessageBox.confirm(`将为 ${selected.length} 项任务设置执行人，确认应用这些分工吗？`, '确认分工', { type: 'warning' })
  } catch { return }
  confirming.value = true
  try {
    await assignmentApi.confirm(projectId, draft.value.id, selected)
    ElMessage.success(`已分配 ${selected.length} 项任务`)
    await router.push(`/projects/${projectId}`)
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '确认分工失败') }
  finally { confirming.value = false }
}

onMounted(load)
</script>

<template>
  <div v-if="project">
    <div class="page-header">
      <div><router-link :to="`/projects/${projectId}`">← 返回项目看板</router-link><h1>AI 智能分工</h1><p>参考成员技能、可用时间、现有负载和学习目标；项目负责人最终确认任务执行人。</p></div>
    </div>
    <el-card style="margin-bottom: 20px">
      <div class="page-header" style="margin-bottom: 0">
        <div><strong>生成分工建议</strong><p class="muted">当前有 {{ eligibleTasks.length }} 项待开始且未分配的任务。每次最多分析 20 项；生成草稿不会修改任务。</p></div>
        <el-button type="primary" :loading="generating" :disabled="!eligibleTasks.length" @click="generate">生成建议</el-button>
      </div>
      <div v-if="drafts.some(item => item.status === 'pending')" style="margin-top: 16px">
        <el-select :model-value="draft?.id" placeholder="选择未确认草稿" style="width: 240px" @change="(id: number) => selectDraft(drafts.find(item => item.id === id) || null)">
          <el-option v-for="item in drafts.filter(value => value.status === 'pending')" :key="item.id" :value="item.id" :label="formatBeijingTime(item.created_at)" />
        </el-select>
      </div>
    </el-card>
    <template v-if="draft">
      <el-alert :title="draft.suggestion.summary || '分工建议'" type="info" :closable="false" style="margin-bottom: 18px" />
      <el-card v-for="row in rows" :key="row.task_id" style="margin-bottom: 14px">
        <div style="display: flex; gap: 14px; align-items: flex-start">
          <el-checkbox v-model="row.selected" style="margin-top: 2px" />
          <div style="flex: 1; min-width: 0">
            <strong>{{ taskTitle(row.task_id) }}</strong>
            <p class="muted">AI 推荐：{{ memberName(draft.suggestion.recommendations.find(item => item.task_id === row.task_id)?.assignee_id || 0) }}</p>
            <p>{{ row.reason }}</p>
            <el-alert v-if="row.risk_note" :title="row.risk_note" type="warning" :closable="false" style="margin-bottom: 12px" />
            <el-select v-model="row.assignee_id" :disabled="!row.selected" placeholder="选择任务执行人" style="width: 280px; max-width: 100%">
              <el-option v-for="member in activeMembers" :key="member.user.id" :value="member.user.id" :label="member.user.name" />
            </el-select>
          </div>
        </div>
      </el-card>
      <el-button type="primary" :loading="confirming" @click="confirm">确认所选分工</el-button>
    </template>
  </div>
</template>
