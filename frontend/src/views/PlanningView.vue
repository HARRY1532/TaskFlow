<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { projectApi } from '../api/project'
import { planningApi } from '../api/planning'
import { formatBeijingTime } from '../utils/date'
import { useAuthStore } from '../stores/auth'
import type { PlannedTask, PlanningConfirmTask, PlanningDraft, Project } from '../types'

type EditableTask = PlanningConfirmTask & { selected: boolean; estimated_hours: number; required_skills: string[]; rationale: string }
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const projectId = Number(route.params.id)
const project = ref<Project | null>(null)
const draft = ref<PlanningDraft | null>(null)
const drafts = ref<PlanningDraft[]>([])
const tasks = ref<EditableTask[]>([])
const projectForm = reactive({ name: '', goal: '', requirements: '', tech_stack: '', start_date: null as string | null, end_date: null as string | null })
const savingProject = ref(false)
const generating = ref(false)
const confirming = ref(false)

function loadDraft(value: PlanningDraft | null) {
  draft.value = value
  tasks.value = value?.suggestion.tasks.map((item: PlannedTask, index: number) => ({
    source_index: index, selected: true, title: item.title, description: item.description,
    acceptance_criteria: item.acceptance_criteria, depends_on: [...item.depends_on],
    estimated_hours: item.estimated_hours, required_skills: item.required_skills, rationale: item.rationale,
  })) || []
}
async function load() {
  try {
    project.value = await projectApi.get(projectId)
    if (project.value.owner_id !== auth.user?.id) {
      ElMessage.error('只有项目负责人可以使用 AI 任务拆解')
      await router.replace(`/projects/${projectId}`)
      return
    }
    drafts.value = await planningApi.drafts(projectId)
    if (project.value) Object.assign(projectForm, {
      name: project.value.name, goal: project.value.goal, requirements: project.value.requirements,
      tech_stack: project.value.tech_stack, start_date: project.value.start_date, end_date: project.value.end_date,
    })
    loadDraft(drafts.value.find(item => item.status === 'pending') || null)
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载规划页面失败') }
}
async function saveProject() {
  savingProject.value = true
  try {
    project.value = await projectApi.update(projectId, projectForm)
    ElMessage.success('项目需求已保存')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '保存需求失败') }
  finally { savingProject.value = false }
}
async function generate() {
  generating.value = true
  try {
    const result = await planningApi.suggest(projectId)
    loadDraft(result)
    drafts.value.unshift(result)
    ElMessage.success('已生成可编辑的任务草稿')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '生成任务建议失败') }
  finally { generating.value = false }
}
function onSelectionChange(changed: EditableTask) {
  if (!changed.selected) {
    for (const item of tasks.value) item.depends_on = item.depends_on.filter(index => index !== changed.source_index)
  }
}
function selectDraft(id: number) { loadDraft(drafts.value.find(item => item.id === id) || null) }
async function confirm() {
  if (!draft.value) return
  const selected = tasks.value.filter(item => item.selected).map(item => ({
    source_index: item.source_index, title: item.title.trim(), description: item.description,
    acceptance_criteria: item.acceptance_criteria, estimated_hours: item.estimated_hours,
    required_skills: item.required_skills, depends_on: item.depends_on,
  }))
  if (!selected.length) { ElMessage.error('请至少选择一项任务'); return }
  if (selected.some(item => !item.title)) { ElMessage.error('任务标题必须有实际内容'); return }
  confirming.value = true
  try {
    await planningApi.confirm(projectId, draft.value.id, selected)
    ElMessage.success(`已创建 ${selected.length} 项任务`)
    await router.push(`/projects/${projectId}`)
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '确认任务失败') }
  finally { confirming.value = false }
}
onMounted(load)
</script>

<template>
  <div v-if="project" class="planning-page">
    <div class="page-header">
      <div><router-link :to="`/projects/${projectId}`">← 返回项目看板</router-link><h1>AI 任务拆解</h1><p>基于项目需求生成草稿，由项目负责人审核后创建任务。</p></div>
    </div>
    <el-card style="margin-bottom: 20px">
      <h3>项目需求</h3>
      <el-form label-position="top" @submit.prevent="saveProject">
        <el-form-item label="项目目标"><el-input v-model="projectForm.goal" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="详细需求"><el-input v-model="projectForm.requirements" type="textarea" :rows="6" maxlength="10000" show-word-limit placeholder="描述功能范围、用户场景和验收要求" /></el-form-item>
        <el-form-item label="技术栈"><el-input v-model="projectForm.tech_stack" /></el-form-item>
        <el-button type="primary" native-type="submit" :loading="savingProject">保存项目需求</el-button>
      </el-form>
    </el-card>
    <el-card style="margin-bottom: 20px">
      <div class="page-header" style="margin-bottom: 0">
        <div><h3 style="margin: 0 0 6px">生成任务建议</h3><p class="muted">建议只生成草稿，确认前不会创建任务。每次生成会使用已保存的项目需求。</p></div>
        <el-button type="primary" :loading="generating" :disabled="!project.goal.trim() && !project.requirements.trim()" @click="generate">生成建议</el-button>
      </div>
      <p v-if="draft" class="muted">当前草稿生成于 {{ formatBeijingTime(draft.created_at) }}（北京时间）</p>
      <el-select v-if="drafts.some(item => item.status === 'pending')" :model-value="draft?.id" placeholder="选择未确认草稿" style="width: 220px" @change="selectDraft">
        <el-option v-for="item in drafts.filter(value => value.status === 'pending')" :key="item.id" :label="formatBeijingTime(item.created_at)" :value="item.id" />
      </el-select>
    </el-card>
    <template v-if="draft">
      <el-alert :title="draft.suggestion.summary" type="info" :closable="false" style="margin-bottom: 18px" />
      <el-card v-for="item in tasks" :key="item.source_index" style="margin-bottom: 14px">
        <div class="page-header" style="margin-bottom: 10px">
          <el-checkbox v-model="item.selected" :label="`创建任务 ${item.source_index + 1}`" @change="onSelectionChange(item)" />
          <el-tag type="info">预计 {{ item.estimated_hours }} 小时</el-tag>
        </div>
        <el-form label-position="top">
          <el-form-item label="任务标题"><el-input v-model="item.title" maxlength="160" :disabled="!item.selected" /></el-form-item>
          <el-form-item label="任务描述"><el-input v-model="item.description" type="textarea" :rows="2" :disabled="!item.selected" /></el-form-item>
          <el-form-item label="验收条件"><el-input v-model="item.acceptance_criteria" type="textarea" :rows="2" :disabled="!item.selected" /></el-form-item>
          <el-form-item label="预计工时（小时）"><el-input-number v-model="item.estimated_hours" :min="1" :max="80" :disabled="!item.selected" /></el-form-item>
          <el-form-item label="所需技能"><el-select v-model="item.required_skills" multiple filterable allow-create default-first-option :disabled="!item.selected" placeholder="输入技能并按 Enter" style="width: 100%" /></el-form-item>
          <el-form-item label="依赖本次建议中的任务"><el-select v-model="item.depends_on" multiple clearable :disabled="!item.selected" placeholder="无前置任务" style="width: 100%">
            <el-option v-for="candidate in tasks.filter(other => other.selected && other.source_index !== item.source_index)" :key="candidate.source_index" :label="candidate.title" :value="candidate.source_index" />
          </el-select></el-form-item>
        </el-form>
        <p class="muted">建议依据：{{ item.rationale }}</p>
      </el-card>
      <div style="display: flex; justify-content: flex-end; margin: 18px 0 36px"><el-button type="primary" :loading="confirming" @click="confirm">确认所选任务并创建</el-button></div>
    </template>
  </div>
</template>
