<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { projectApi } from '../api/project'
import { taskApi } from '../api/task'
import { requirementsApi } from '../api/requirements'
import { useAuthStore } from '../stores/auth'
import type { Project, Requirement, RequirementInput, RequirementMatchSuggestion, Task } from '../types'

const route = useRoute()
const auth = useAuthStore()
const projectId = computed(() => Number(route.params.id))
const project = ref<Project | null>(null)
const requirements = ref<Requirement[]>([])
const tasks = ref<Task[]>([])
const loading = ref(false)
const saving = ref(false)
const editDialog = ref(false)
const linksDialog = ref(false)
const editingId = ref<number | null>(null)
const linking = ref<Requirement | null>(null)
const selectedTaskIds = ref<number[]>([])
const suggestion = ref<RequirementMatchSuggestion | null>(null)
const suggesting = ref(false)
const form = reactive<RequirementInput>({
  title: '', description: '', acceptance_criteria: '', priority: 'medium', status: 'active',
})
const isOwner = computed(() => project.value?.owner_id === auth.user?.id)
const taskById = (id: number) => tasks.value.find(task => task.id === id)
const doneCount = (requirement: Requirement) => requirement.task_ids.filter(id => taskById(id)?.status === 'done').length
const priorityLabel = { low: '低优先级', medium: '中优先级', high: '高优先级' }

async function load() {
  loading.value = true
  try {
    ;[project.value, requirements.value, tasks.value] = await Promise.all([
      projectApi.get(projectId.value), requirementsApi.list(projectId.value), taskApi.list(projectId.value),
    ])
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载需求失败') }
  finally { loading.value = false }
}
function openCreate() {
  editingId.value = null
  Object.assign(form, { title: '', description: '', acceptance_criteria: '', priority: 'medium', status: 'active' })
  editDialog.value = true
}
function openEdit(requirement: Requirement) {
  editingId.value = requirement.id
  Object.assign(form, {
    title: requirement.title, description: requirement.description,
    acceptance_criteria: requirement.acceptance_criteria,
    priority: requirement.priority, status: requirement.status,
  })
  editDialog.value = true
}
async function save() {
  if (!form.title.trim()) { ElMessage.error('需求标题必须填写实际内容'); return }
  saving.value = true
  try {
    const payload = { ...form, title: form.title.trim() }
    if (editingId.value === null) await requirementsApi.create(projectId.value, payload)
    else await requirementsApi.update(projectId.value, editingId.value, payload)
    requirements.value = await requirementsApi.list(projectId.value)
    editDialog.value = false
    ElMessage.success('需求已保存')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '保存需求失败') }
  finally { saving.value = false }
}
function openLinks(requirement: Requirement) {
  linking.value = requirement
  selectedTaskIds.value = [...requirement.task_ids]
  suggestion.value = null
  linksDialog.value = true
}
async function suggestLinks() {
  if (!linking.value || suggesting.value) return
  suggesting.value = true
  try {
    const result = await requirementsApi.suggestTasks(projectId.value, linking.value.id)
    suggestion.value = result
    selectedTaskIds.value = [...new Set([
      ...selectedTaskIds.value, ...result.recommendations.map(item => item.task_id),
    ])]
    if (!result.recommendations.length) ElMessage.info('AI 未找到明确相关的未关联任务')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '生成建议失败') }
  finally { suggesting.value = false }
}
async function saveLinks() {
  if (!linking.value) return
  saving.value = true
  try {
    await requirementsApi.linkTasks(projectId.value, linking.value.id, selectedTaskIds.value, suggestion.value?.context_signature)
    requirements.value = await requirementsApi.list(projectId.value)
    linksDialog.value = false
    ElMessage.success('关联任务已保存')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '关联任务失败') }
  finally { saving.value = false }
}
async function remove(requirement: Requirement) {
  try {
    await ElMessageBox.confirm(
      `删除需求“${requirement.title}”会移除与任务的关联，任务本身会保留。确定删除吗？`,
      '删除需求', { type: 'warning' },
    )
  } catch { return }
  try {
    await requirementsApi.remove(projectId.value, requirement.id)
    requirements.value = await requirementsApi.list(projectId.value)
    ElMessage.success('需求已删除')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '删除需求失败') }
}

watch(projectId, load)
onMounted(load)
</script>

<template>
  <div>
    <div class="page-header">
      <div><router-link :to="`/projects/${projectId}`">← 返回项目看板</router-link><h1>项目需求</h1>
        <p>{{ project?.name || '加载中' }} · 将功能需求与执行任务关联，便于回看交付范围。</p></div>
      <el-button v-if="isOwner" type="primary" @click="openCreate">新增需求</el-button>
    </div>
    <p class="muted">关联任务的完成数量只反映任务状态；需求是否满足验收条件仍需人工判断。</p>
    <el-skeleton v-if="loading" :rows="4" animated />
    <el-empty v-else-if="!requirements.length" description="暂无独立需求。项目负责人可以新增需求，再关联任务。" />
    <div v-else style="display: grid; gap: 16px">
      <el-card v-for="requirement in requirements" :key="requirement.id">
        <div style="display: flex; justify-content: space-between; gap: 16px; align-items: flex-start">
          <div><h3 style="margin: 0 0 8px">{{ requirement.title }}</h3>
            <el-tag size="small" :type="requirement.priority === 'high' ? 'danger' : requirement.priority === 'low' ? 'info' : 'warning'">{{ priorityLabel[requirement.priority] }}</el-tag>
            <el-tag size="small" :type="requirement.status === 'archived' ? 'info' : 'success'" style="margin-left: 8px">{{ requirement.status === 'archived' ? '已归档' : '进行中' }}</el-tag>
          </div>
          <div v-if="isOwner" style="display: flex; gap: 8px; flex-wrap: wrap">
            <el-button size="small" @click="openEdit(requirement)">编辑</el-button>
            <el-button size="small" @click="openLinks(requirement)">关联任务</el-button>
            <el-button size="small" type="danger" text @click="remove(requirement)">删除</el-button>
          </div>
        </div>
        <p v-if="requirement.description" style="white-space: pre-wrap">{{ requirement.description }}</p>
        <p v-if="requirement.acceptance_criteria" style="white-space: pre-wrap"><strong>验收标准：</strong>{{ requirement.acceptance_criteria }}</p>
        <p class="muted">关联任务：{{ requirement.task_ids.length }} 项 · 已完成任务：{{ doneCount(requirement) }} 项</p>
        <el-space v-if="requirement.task_ids.length" wrap>
          <el-tag v-for="taskId in requirement.task_ids" :key="taskId" :type="taskById(taskId)?.status === 'done' ? 'success' : 'info'">
            {{ taskById(taskId)?.title || '已删除任务' }}
          </el-tag>
        </el-space>
        <p v-else class="muted">尚未关联执行任务。</p>
      </el-card>
    </div>
    <el-dialog v-model="editDialog" :title="editingId === null ? '新增需求' : '编辑需求'" width="580px">
      <el-form label-position="top" @submit.prevent="save">
        <el-form-item label="需求标题"><el-input v-model="form.title" maxlength="160" show-word-limit /></el-form-item>
        <el-form-item label="需求描述"><el-input v-model="form.description" type="textarea" :rows="4" maxlength="5000" show-word-limit /></el-form-item>
        <el-form-item label="验收标准"><el-input v-model="form.acceptance_criteria" type="textarea" :rows="3" maxlength="3000" show-word-limit /></el-form-item>
        <el-form-item label="优先级"><el-select v-model="form.priority"><el-option label="低" value="low" /><el-option label="中" value="medium" /><el-option label="高" value="high" /></el-select></el-form-item>
        <el-form-item label="状态"><el-select v-model="form.status"><el-option label="进行中" value="active" /><el-option label="已归档" value="archived" /></el-select></el-form-item>
        <el-button type="primary" native-type="submit" :loading="saving">保存需求</el-button>
      </el-form>
    </el-dialog>
    <el-dialog v-model="linksDialog" :title="`关联任务：${linking?.title || ''}`" width="520px">
      <p class="muted">一个需求可关联多个任务，任务也可服务于多个需求。这里只建立对应关系，不改变任务状态。</p>
      <p class="muted">生成 AI 建议会把此需求和当前项目任务的标题、描述、验收条件发送给 DeepSeek；建议不会自动保存。</p>
      <el-button :loading="suggesting" :disabled="!tasks.length || saving || linking?.status === 'archived'" @click="suggestLinks">AI 推荐相关任务</el-button>
      <div v-if="suggestion" style="margin: 16px 0; padding: 14px; border-radius: 8px; background: var(--el-fill-color-light)">
        <strong>AI 建议</strong>
        <p>{{ suggestion.summary }}</p>
        <p v-if="!suggestion.recommendations.length" class="muted">没有推荐任务，请按需要手动选择。</p>
        <div v-for="item in suggestion.recommendations" :key="item.task_id" style="padding: 8px 0; border-top: 1px solid var(--el-border-color-lighter)">
          <el-checkbox v-model="selectedTaskIds" :value="item.task_id">{{ taskById(item.task_id)?.title || '任务已变化' }}</el-checkbox>
          <p class="muted" style="margin: 4px 0 0 24px">{{ item.reason }}</p>
        </div>
      </div>
      <p class="muted">最终关联任务（可手动增删）：</p>
      <el-select v-model="selectedTaskIds" multiple filterable clearable placeholder="选择当前项目的任务" style="width: 100%">
        <el-option v-for="task in tasks" :key="task.id" :label="task.title" :value="task.id" />
      </el-select>
      <template #footer><el-button @click="linksDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveLinks">保存关联</el-button></template>
    </el-dialog>
  </div>
</template>
