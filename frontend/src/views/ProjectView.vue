<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { projectApi } from '../api/project'
import { taskApi } from '../api/task'
import { skillsApi } from '../api/skills'
import { weightsApi } from '../api/weights'
import { dependenciesApi } from '../api/dependencies'
import { useAuthStore } from '../stores/auth'
import { formatBeijingTime } from '../utils/date'
import type { ChecklistItem, Invitation, Member, MemberSkillProfile, Project, SkillCategory, Task, TaskDependencies, TaskEvent, TaskReviewAdvice, TaskReviewSnapshot, TaskStatus, TaskWeight, WeightFactors, WeightSuggestion } from '../types'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const projectId = computed(() => Number(route.params.id))
const project = ref<Project | null>(null)
const members = ref<Member[]>([])
const memberSkills = ref<MemberSkillProfile[]>([])
const invitations = ref<Invitation[]>([])
const tasks = ref<Task[]>([])
const weights = ref<TaskWeight[]>([])
const dependencies = ref<TaskDependencies[]>([])
const dependencyDialog = ref(false)
const dependencyTask = ref<Task | null>(null)
const selectedDependencies = ref<number[]>([])
const savingDependencies = ref(false)
const createDialog = ref(false)
const editingTaskId = ref<number | null>(null)
const inviteDialog = ref(false)
const assignDialog = ref(false)
const transferDialog = ref(false)
const newOwnerId = ref<number | null>(null)
const assigningTask = ref<Task | null>(null)
const selectedAssigneeId = ref<number | null>(null)
const eventDialog = ref(false)
const events = ref<TaskEvent[]>([])
const checklistDialog = ref(false)
const checklistTask = ref<Task | null>(null)
const checklistItems = ref<ChecklistItem[]>([])
const generatingChecklist = ref(false)
const savingChecklist = ref(false)
const submitDialog = ref(false)
const submittingTask = ref<Task | null>(null)
const submitForm = reactive({ note: '', url: '', code_url: '', test_url: '', test_note: '' })
const repositoryDialog = ref(false)
const repositoryUrl = ref('')
const savingRepository = ref(false)
const verifyingTaskId = ref<number | null>(null)
const reviewDialog = ref(false)
const reviewedTask = ref<Task | null>(null)
const reviewSnapshots = ref<TaskReviewSnapshot[]>([])
const loadingReviews = ref(false)
const capturingReview = ref(false)
const generatingAdviceId = ref<number | null>(null)
const confirmingAdviceId = ref<number | null>(null)
const reviewAdvice = ref<Record<number, TaskReviewAdvice[]>>({})
const weightDialog = ref(false)
const weightedTask = ref<Task | null>(null)
const weightSuggestion = ref<WeightSuggestion | null>(null)
const suggestingWeight = ref(false)
const savingWeight = ref(false)
const weightForm = reactive({ complexity: 3, estimated_hours: 8, importance: 3, risk: 3, confirmed_score: 0, adjustment_reason: '' })
const inviteEmail = ref('')
const saving = ref(false)
const taskForm = reactive({ title: '', description: '', priority: 'medium', due_date: '', acceptance_criteria: '', estimated_hours: null as number | null, required_skills_text: '', assignee_id: null as number | null })
const isOwner = computed(() => project.value?.owner_id === auth.user?.id)
const skillCategoryLabel: Record<SkillCategory, string> = {
  language: '编程语言', frontend: '前端', backend: '后端',
  database: '数据库', testing: '测试', other: '其他',
}
const columns: { key: TaskStatus; label: string }[] = [
  { key: 'todo', label: '待开始' }, { key: 'in_progress', label: '进行中' },
  { key: 'review', label: '待验收' }, { key: 'done', label: '已完成' },
]
const tasksFor = (status: TaskStatus) => tasks.value.filter(t => t.status === status)
const weightFor = (taskId: number) => weights.value.find(weight => weight.task_id === taskId)
const dependsOn = (taskId: number) => dependencies.value.find(item => item.task_id === taskId)?.depends_on_ids || []
const taskTitle = (taskId: number) => tasks.value.find(item => item.id === taskId)?.title || '已删除任务'
function openDependencies(task: Task) {
  dependencyTask.value = task
  selectedDependencies.value = [...dependsOn(task.id)]
  dependencyDialog.value = true
}
async function saveDependencies() {
  if (!dependencyTask.value) return
  savingDependencies.value = true
  try {
    await dependenciesApi.save(projectId.value, dependencyTask.value.id, selectedDependencies.value)
    dependencies.value = await dependenciesApi.list(projectId.value)
    dependencyDialog.value = false
    ElMessage.success('任务依赖已保存')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '保存依赖失败') }
  finally { savingDependencies.value = false }
}
const weightFactors = (): WeightFactors => ({
  complexity: weightForm.complexity, estimated_hours: weightForm.estimated_hours,
  importance: weightForm.importance, risk: weightForm.risk,
})

function openWeight(task: Task) {
  weightedTask.value = task
  const saved = weightFor(task.id)
  Object.assign(weightForm, saved ? {
    complexity: saved.complexity, estimated_hours: saved.estimated_hours,
    importance: saved.importance, risk: saved.risk,
    confirmed_score: saved.confirmed_score, adjustment_reason: saved.adjustment_reason,
  } : { complexity: 3, estimated_hours: task.estimated_hours || 8, importance: 3, risk: 3, confirmed_score: 0, adjustment_reason: '' })
  weightSuggestion.value = saved ? {
    ...weightFactors(), suggested_score: saved.suggested_score, rationale: saved.rationale,
  } : null
  weightDialog.value = true
}
function invalidateWeightSuggestion() { weightSuggestion.value = null }
async function suggestWeight() {
  if (!weightedTask.value) return
  suggestingWeight.value = true
  try {
    weightSuggestion.value = await weightsApi.suggest(projectId.value, weightedTask.value.id, weightFactors())
    weightForm.confirmed_score = weightSuggestion.value.suggested_score
    weightForm.adjustment_reason = ''
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '计算建议失败') }
  finally { suggestingWeight.value = false }
}
async function confirmWeight() {
  if (!weightedTask.value || !weightSuggestion.value) return
  if (weightForm.confirmed_score !== weightSuggestion.value.suggested_score && !weightForm.adjustment_reason.trim()) {
    ElMessage.error('调整建议分值时请填写原因')
    return
  }
  savingWeight.value = true
  try {
    await weightsApi.confirm(projectId.value, weightedTask.value.id, {
      ...weightFactors(), confirmed_score: weightForm.confirmed_score,
      adjustment_reason: weightForm.adjustment_reason,
    })
    await refreshTasks()
    weightDialog.value = false
    ElMessage.success('任务权重已确认')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '保存权重失败') }
  finally { savingWeight.value = false }
}

async function load() {
  try {
    const id = projectId.value
    ;[project.value, members.value, tasks.value, weights.value, dependencies.value] = await Promise.all([
      projectApi.get(id), projectApi.members(id), taskApi.list(id), weightsApi.list(id), dependenciesApi.list(id),
    ])
    invitations.value = isOwner.value ? await projectApi.invitations(id) : []
    memberSkills.value = isOwner.value ? await skillsApi.project(id) : []
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载失败') }
}
async function refreshTasks() {
  ;[tasks.value, weights.value, dependencies.value] = await Promise.all([
    taskApi.list(projectId.value), weightsApi.list(projectId.value), dependenciesApi.list(projectId.value),
  ])
}
function openRepository() {
  repositoryUrl.value = project.value?.github_repo_url || ''
  repositoryDialog.value = true
}
async function saveRepository() {
  savingRepository.value = true
  try {
    project.value = await projectApi.setRepository(projectId.value, repositoryUrl.value.trim() || null)
    repositoryDialog.value = false
    ElMessage.success(project.value.github_repo_url ? '公开仓库已绑定' : '已移除仓库')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '保存仓库失败') }
  finally { savingRepository.value = false }
}
async function refreshCode(task: Task) {
  verifyingTaskId.value = task.id
  try {
    await taskApi.refreshCodeEvidence(projectId.value, task.id)
    await refreshTasks()
    ElMessage.success('GitHub 信息已更新')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '核验失败') }
  finally { verifyingTaskId.value = null }
}
async function openReview(task: Task) {
  reviewedTask.value = task
  reviewSnapshots.value = []
  reviewDialog.value = true
  loadingReviews.value = true
  try { await loadReviewData(task.id) }
  catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载 PR 证据失败') }
  finally { loadingReviews.value = false }
}
async function loadReviewData(taskId: number) {
  reviewSnapshots.value = await taskApi.reviewSnapshots(projectId.value, taskId)
  const entries = await Promise.all(reviewSnapshots.value.map(async snapshot =>
    [snapshot.id, await taskApi.reviewAdvice(projectId.value, taskId, snapshot.id)] as const))
  reviewAdvice.value = Object.fromEntries(entries)
}
async function captureReview() {
  if (!reviewedTask.value) return
  capturingReview.value = true
  try {
    await taskApi.captureReviewSnapshot(projectId.value, reviewedTask.value.id)
    await loadReviewData(reviewedTask.value.id)
    await refreshTasks()
    ElMessage.success('已读取并保存 PR 改动')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '读取 PR 改动失败') }
  finally { capturingReview.value = false }
}
async function generateReviewAdvice(snapshot: TaskReviewSnapshot) {
  if (!reviewedTask.value || !snapshot.is_current || confirmingAdviceId.value !== null || generatingAdviceId.value !== null) return
  confirmingAdviceId.value = snapshot.id
  try {
    await ElMessageBox.confirm(
      '即将把任务描述、验收条件、开发清单、测试说明，以及此公开 PR 的文件路径和文本补丁发送给 DeepSeek。请先检查下方补丁，确认没有密钥、个人信息或其他不宜外传的内容。自动检测可能遗漏。',
      '信息安全提示（1/2）',
      { type: 'warning', confirmButtonText: '我已检查，继续', cancelButtonText: '取消' },
    )
    await ElMessageBox.prompt(
      '再次确认外部发送。DeepSeek API 按官方文档为无会话状态；本系统无法保证删除服务方日志或缓存。若确认，请输入“发送至 DeepSeek”。',
      '最终确认（2/2）',
      { type: 'warning', confirmButtonText: '生成 AI 建议', cancelButtonText: '取消',
        inputValidator: value => value.trim() === '发送至 DeepSeek' || '请输入“发送至 DeepSeek”' },
    )
  } catch { return }
  finally { confirmingAdviceId.value = null }
  generatingAdviceId.value = snapshot.id
  try {
    await taskApi.generateReviewAdvice(projectId.value, reviewedTask.value.id, snapshot.id)
    reviewAdvice.value[snapshot.id] = await taskApi.reviewAdvice(projectId.value, reviewedTask.value.id, snapshot.id)
    ElMessage.success('AI 验收建议已生成，请人工核实')
  } catch (error) {
    const message = error instanceof Error ? error.message : 'AI 分析失败'
    if (message.startsWith('敏感信息预警：')) await ElMessageBox.alert(message, '敏感信息预警', { type: 'warning' })
    else ElMessage.error(message)
  } finally { generatingAdviceId.value = null }
}
async function confirmProjectAction(action: 'delete' | 'leave') {
  if (!project.value) return null
  const name = project.value.name
  const label = action === 'delete' ? '删除项目' : '退出项目'
  const consequences = action === 'delete'
    ? `删除“${name}”后，项目、成员关系、任务、成果和验收记录将永久删除且无法恢复；管理员仍能查看删除通知。`
    : `退出“${name}”后，你将无法查看项目；分配给你的未完成任务会退回未分配。重新加入需要项目负责人再次邀请。`
  try {
    await ElMessageBox.confirm(consequences, `${label}：后果确认（1/2）`, {
      type: 'warning', confirmButtonText: '我已了解，继续', cancelButtonText: '取消',
    })
    const result = await ElMessageBox.prompt(`请再次确认，并输入项目名称“${name}”`, `${label}：最终确认（2/2）`, {
      type: 'warning', confirmButtonText: `确认${label}`, cancelButtonText: '取消',
      inputValidator: value => value.trim() === name || '项目名称不一致',
    })
    return result.value.trim()
  } catch { return null }
}
async function deleteProject() {
  const confirmation = await confirmProjectAction('delete')
  if (!confirmation) return
  try {
    await projectApi.remove(projectId.value, confirmation)
    ElMessage.success('项目已删除')
    await router.push('/projects')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '删除失败') }
}
async function leaveProject() {
  const confirmation = await confirmProjectAction('leave')
  if (!confirmation) return
  try {
    await projectApi.leave(projectId.value, confirmation)
    ElMessage.success('已退出项目')
    await router.push('/projects')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '退出失败') }
}
function openTransfer() {
  newOwnerId.value = null
  transferDialog.value = true
}
async function transferOwner() {
  if (newOwnerId.value === null) { ElMessage.error('请选择接任项目负责人'); return }
  saving.value = true
  try {
    project.value = await projectApi.transferOwner(projectId.value, newOwnerId.value)
    members.value = await projectApi.members(projectId.value)
    memberSkills.value = isOwner.value ? await skillsApi.project(projectId.value) : []
    transferDialog.value = false
    ElMessage.success('项目负责人已转让；现在可以退出项目')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '转让失败') }
  finally { saving.value = false }
}
function openCreateTask() {
  editingTaskId.value = null
  Object.assign(taskForm, { title: '', description: '', priority: 'medium', due_date: '', acceptance_criteria: '', estimated_hours: null, required_skills_text: '', assignee_id: null })
  createDialog.value = true
}
function openEditTask(task: Task) {
  editingTaskId.value = task.id
  Object.assign(taskForm, {
    title: task.title, description: task.description, priority: task.priority,
    due_date: task.due_date || '', acceptance_criteria: task.acceptance_criteria,
    estimated_hours: task.estimated_hours, required_skills_text: task.required_skills.join('、'),
    assignee_id: task.assignee_id,
  })
  createDialog.value = true
}
async function saveTask() {
  taskForm.title = taskForm.title.trim()
  if (!taskForm.title) { ElMessage.error('任务标题必须填写实际内容'); return }
  saving.value = true
  try {
    const { required_skills_text, ...fields } = taskForm
    const payload = {
      ...fields, due_date: taskForm.due_date || null,
      required_skills: required_skills_text.split(/[、,，]/).map(item => item.trim()).filter(Boolean),
    }
    if (editingTaskId.value === null) await taskApi.create(projectId.value, payload)
    else await taskApi.update(projectId.value, editingTaskId.value, payload)
    createDialog.value = false
    await refreshTasks()
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '保存失败') }
  finally { saving.value = false }
}
async function deleteTask(task: Task) {
  try {
    await ElMessageBox.confirm(`确定删除“${task.title}”吗？`, '删除任务', { type: 'warning' })
    await taskApi.remove(projectId.value, task.id)
    await refreshTasks()
  } catch (error) { if (error instanceof Error) ElMessage.error(error.message) }
}
async function invite() {
  saving.value = true
  try {
    await projectApi.invite(projectId.value, inviteEmail.value)
    invitations.value = await projectApi.invitations(projectId.value)
    inviteDialog.value = false
    inviteEmail.value = ''
    ElMessage.success('邀请已发送，待对方同意')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '邀请失败') }
  finally { saving.value = false }
}
async function cancelInvitation(invitation: Invitation) {
  try {
    await projectApi.cancelInvitation(projectId.value, invitation.id)
    invitations.value = await projectApi.invitations(projectId.value)
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '撤销失败') }
}
function openAssign(task: Task) {
  assigningTask.value = task
  selectedAssigneeId.value = task.assignee_id
  assignDialog.value = true
}
async function saveAssignment() {
  if (!assigningTask.value) return
  const assigneeId = selectedAssigneeId.value
  if (assigneeId === null || !members.value.some(m => m.user.id === assigneeId && m.user.is_active)) {
    ElMessage.error('请选择项目成员')
    return
  }
  saving.value = true
  try {
    await taskApi.update(projectId.value, assigningTask.value.id, { assignee_id: assigneeId })
    assignDialog.value = false
    await refreshTasks()
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '分配失败') }
  finally { saving.value = false }
}
async function start(task: Task) {
  try { await taskApi.start(projectId.value, task.id); await refreshTasks() }
  catch (error) { ElMessage.error(error instanceof Error ? error.message : '操作失败') }
}
function openSubmit(task: Task) {
  submittingTask.value = task
  Object.assign(submitForm, { note: task.evidence_note || '', url: task.evidence_url || '',
    code_url: task.code_url || '', test_url: task.test_url || '', test_note: task.test_note || '' })
  submitDialog.value = true
}
async function submit() {
  if (!submittingTask.value) return
  if (!Object.values(submitForm).some(value => value.trim())) { ElMessage.error('请填写至少一项成果或测试证据'); return }
  saving.value = true
  try {
    await taskApi.submit(projectId.value, submittingTask.value.id, {
      note: submitForm.note.trim(), url: submitForm.url.trim() || null,
      code_url: submitForm.code_url.trim() || null, test_url: submitForm.test_url.trim() || null,
      test_note: submitForm.test_note.trim(),
    })
    submitDialog.value = false
    await refreshTasks()
    ElMessage.success('成果已提交验收')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '提交失败') }
  finally { saving.value = false }
}
function openChecklist(task: Task) {
  checklistTask.value = task
  checklistItems.value = task.development_checklist.map(item => ({ ...item }))
  checklistDialog.value = true
}
async function generateChecklist() {
  if (!checklistTask.value) return
  if (checklistItems.value.length) {
    try { await ElMessageBox.confirm('重新生成会覆盖当前清单及勾选状态。确定继续吗？', '重新生成开发清单', { type: 'warning' }) }
    catch { return }
  }
  generatingChecklist.value = true
  try {
    checklistItems.value = await taskApi.generateChecklist(projectId.value, checklistTask.value.id)
    await refreshTasks()
    ElMessage.success('开发清单已生成')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '生成失败') }
  finally { generatingChecklist.value = false }
}
async function saveChecklist() {
  if (!checklistTask.value) return
  savingChecklist.value = true
  try {
    await taskApi.saveChecklist(projectId.value, checklistTask.value.id, checklistItems.value)
    await refreshTasks()
    ElMessage.success('清单进度已保存')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '保存失败') }
  finally { savingChecklist.value = false }
}
async function decide(task: Task, accept: boolean) {
  try {
    const { value } = await ElMessageBox.prompt(accept ? '验收说明（可留空）' : '驳回原因', accept ? '验收任务' : '驳回任务', { inputType: 'textarea', inputValue: '' })
    if (accept) await taskApi.accept(projectId.value, task.id, value)
    else await taskApi.reject(projectId.value, task.id, value)
    await refreshTasks()
  } catch (error) { if (error instanceof Error) ElMessage.error(error.message) }
}
async function showEvents(task: Task) {
  try { events.value = await taskApi.events(projectId.value, task.id); eventDialog.value = true }
  catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载失败') }
}
watch(projectId, load)
onMounted(load)
</script>

<template>
  <div v-if="project">
    <div class="page-header">
      <div><router-link to="/projects">← 我的项目</router-link><h1>{{ project.name }}</h1><p>{{ project.goal || '暂无项目目标' }}</p></div>
      <div v-if="isOwner">
        <el-button @click="inviteDialog = true">邀请成员</el-button>
        <el-button :disabled="!members.some(member => member.user.id !== auth.user?.id && member.user.is_active)" @click="openTransfer">转让项目负责人</el-button>
        <el-button type="primary" @click="openCreateTask">新建任务</el-button>
        <router-link :to="`/projects/${projectId}/planning`"><el-button>AI 任务拆解</el-button></router-link>
        <router-link :to="`/projects/${projectId}/assignments`"><el-button>AI 智能分工</el-button></router-link>
        <router-link :to="`/projects/${projectId}/progress`"><el-button>进度诊断</el-button></router-link>
        <router-link :to="`/projects/${projectId}/analytics`"><el-button>数据分析</el-button></router-link>
        <el-button type="danger" plain @click="deleteProject">删除项目</el-button>
      </div>
      <div v-else>
        <router-link :to="`/projects/${projectId}/analytics`"><el-button>数据分析</el-button></router-link>
        <el-button type="danger" plain @click="leaveProject">退出项目</el-button>
      </div>
    </div>
    <el-card style="margin-bottom: 20px">
      <strong>项目代码仓库</strong>
      <p v-if="project.github_repo_url"><a :href="project.github_repo_url" target="_blank" rel="noopener noreferrer">{{ project.github_repo_url }}</a></p>
      <p v-else class="muted">尚未绑定公开 GitHub 仓库。绑定后提交代码或 PR 链接时，系统会核对其所属仓库并读取摘要。</p>
      <el-button v-if="isOwner" size="small" @click="openRepository">{{ project.github_repo_url ? '管理仓库' : '绑定仓库' }}</el-button>
    </el-card>
    <el-card style="margin-bottom: 20px">
      <strong>项目成员</strong>
      <p class="muted">项目负责人管理项目和验收成果；任务执行人按任务分别指定。</p>
      <el-space wrap style="margin-left: 16px">
        <el-tag v-for="member in members" :key="member.user.id" :type="member.role === 'owner' ? 'primary' : 'info'">
          {{ member.user.name }}{{ member.role === 'owner' ? ' · 项目负责人' : '' }}{{ !member.user.is_active ? ' · 已停用' : '' }}
        </el-tag>
      </el-space>
    </el-card>
    <el-card v-if="isOwner && invitations.some(item => item.status === 'pending')" style="margin-bottom: 20px">
      <strong>待处理邀请</strong>
      <div v-for="invitation in invitations.filter(item => item.status === 'pending')" :key="invitation.id" style="margin-top: 12px">
        {{ invitation.invited_user_name }} · 已发送
        <el-button size="small" text type="danger" @click="cancelInvitation(invitation)">撤销</el-button>
      </div>
    </el-card>
    <el-card v-if="isOwner" style="margin-bottom: 20px">
      <strong>成员技能画像</strong>
      <p class="muted">成员自行填写，供任务分配参考。</p>
      <el-empty v-if="!memberSkills.length" description="暂无成员画像" />
      <div v-for="member in memberSkills" :key="member.user.id" style="padding: 12px 0; border-top: 1px solid var(--el-border-color-lighter)">
        <strong>{{ member.user.name }}</strong>
        <span class="muted"> · 每周 {{ member.profile.weekly_hours }} 小时{{ member.profile.updated_at ? '' : ' · 尚未填写' }}</span>
        <p v-if="member.profile.learning_goal">学习目标：{{ member.profile.learning_goal }}</p>
        <div v-if="member.profile.skills.length"><el-space wrap>
          <el-tag v-for="(skill, index) in member.profile.skills" :key="index" type="info">{{ skillCategoryLabel[skill.category] }} · {{ skill.name }} · {{ skill.level }} 级</el-tag>
        </el-space></div>
      </div>
    </el-card>
    <div class="board">
      <section v-for="column in columns" :key="column.key" class="column">
        <h3>{{ column.label }} <span class="muted">{{ tasksFor(column.key).length }}</span></h3>
        <article v-for="task in tasksFor(column.key)" :key="task.id" class="task-card">
          <h4>{{ task.title }}</h4>
          <p>{{ task.description || '暂无描述' }}</p>
          <el-tag size="small" :type="task.priority === 'high' ? 'danger' : task.priority === 'low' ? 'info' : 'warning'">{{ task.priority }}</el-tag>
          <el-tag v-if="weightFor(task.id)" size="small" type="success" style="margin-left: 6px">权重 {{ weightFor(task.id)?.confirmed_score }}/100</el-tag>
          <p>任务执行人：{{ task.assignee_name || '未分配' }}<br>截止：{{ task.due_date || '未设置' }}</p>
          <p v-if="task.acceptance_criteria">验收条件：{{ task.acceptance_criteria }}</p>
          <p v-if="task.estimated_hours">预计工时：{{ task.estimated_hours }} 小时</p>
          <p v-if="task.required_skills.length">所需技能：{{ task.required_skills.join('、') }}</p>
          <p v-if="dependsOn(task.id).length">依赖任务：{{ dependsOn(task.id).map(taskTitle).join('、') }}</p>
          <p v-if="task.evidence_note">成果：{{ task.evidence_note }}</p>
          <p v-if="task.evidence_url"><a :href="task.evidence_url" target="_blank" rel="noopener noreferrer">查看成果链接</a></p>
          <p v-if="task.code_url"><a :href="task.code_url" target="_blank" rel="noopener noreferrer">查看代码或 PR</a></p>
          <div v-if="task.code_metadata" style="padding: 10px; border-radius: 8px; background: var(--el-fill-color-light)">
            <strong>{{ task.code_metadata.kind === 'pull' ? `PR #${task.code_metadata.number}` : '提交' }}：{{ task.code_metadata.title }}</strong>
            <p class="muted" style="margin: 4px 0">作者：{{ task.code_metadata.author }} · 状态：{{ task.code_metadata.state }}<br>SHA：{{ task.code_metadata.sha.slice(0, 12) }} · 核验于 {{ formatBeijingTime(task.code_metadata.checked_at) }}</p>
          </div>
          <p v-else-if="task.code_url" class="muted">此链接尚未由 GitHub 核验。</p>
          <p v-if="task.test_url"><a :href="task.test_url" target="_blank" rel="noopener noreferrer">查看测试记录</a></p>
          <p v-if="task.test_note">测试说明：{{ task.test_note }}</p>
          <p v-if="task.development_checklist?.length" class="muted">开发清单：{{ task.development_checklist.filter(item => item.checked).length }}/{{ task.development_checklist.length }} 已完成</p>
          <div class="task-actions">
            <el-button v-if="isOwner && task.status === 'todo'" size="small" @click="openAssign(task)">分配</el-button>
            <el-button v-if="isOwner" size="small" @click="openEditTask(task)">编辑</el-button>
            <el-button v-if="isOwner" size="small" @click="openWeight(task)">{{ weightFor(task.id) ? '调整权重' : '评估权重' }}</el-button>
            <el-button v-if="isOwner" size="small" @click="openDependencies(task)">依赖</el-button>
            <el-button size="small" @click="openChecklist(task)">开发清单</el-button>
            <el-button v-if="task.code_url && project.github_repo_url && (isOwner || task.assignee_id === auth.user?.id)" size="small" :loading="verifyingTaskId === task.id" @click="refreshCode(task)">刷新 GitHub 信息</el-button>
            <el-button v-if="task.code_metadata?.kind === 'pull' && project.github_repo_url" size="small" @click="openReview(task)">PR 改动证据</el-button>
            <el-button v-if="isOwner" size="small" type="danger" text @click="deleteTask(task)">删除</el-button>
            <el-button v-if="task.assignee_id === auth.user?.id && task.status === 'todo'" size="small" type="primary" @click="start(task)">开始</el-button>
            <el-button v-if="task.assignee_id === auth.user?.id && task.status === 'in_progress'" size="small" type="primary" @click="openSubmit(task)">提交成果</el-button>
            <template v-if="isOwner && task.status === 'review'"><el-button size="small" type="success" @click="decide(task, true)">验收</el-button><el-button size="small" type="warning" @click="decide(task, false)">驳回</el-button></template>
            <el-button size="small" text @click="showEvents(task)">记录</el-button>
          </div>
        </article>
      </section>
    </div>
  </div>
  <el-dialog v-model="createDialog" :title="editingTaskId === null ? '新建任务' : '编辑任务'" width="520px">
    <el-form label-position="top" @submit.prevent="saveTask">
      <el-form-item label="标题"><el-input v-model="taskForm.title" /></el-form-item>
      <el-form-item label="描述"><el-input v-model="taskForm.description" type="textarea" /></el-form-item>
      <el-form-item label="优先级"><el-select v-model="taskForm.priority"><el-option label="低" value="low" /><el-option label="中" value="medium" /><el-option label="高" value="high" /></el-select></el-form-item>
      <el-form-item label="任务执行人"><el-select v-model="taskForm.assignee_id" clearable placeholder="暂不分配"><el-option v-for="member in members.filter(item => item.user.is_active)" :key="member.user.id" :label="`${member.user.name}（${member.user.email}）`" :value="member.user.id" /></el-select></el-form-item>
      <el-form-item label="截止日期"><el-date-picker v-model="taskForm.due_date" type="date" value-format="YYYY-MM-DD" placeholder="可选" /></el-form-item>
      <el-form-item label="验收条件"><el-input v-model="taskForm.acceptance_criteria" type="textarea" /></el-form-item>
      <el-form-item label="预计工时（小时）"><el-input-number v-model="taskForm.estimated_hours" :min="1" :max="80" placeholder="可选" /></el-form-item>
      <el-form-item label="所需技能"><el-input v-model="taskForm.required_skills_text" placeholder="用逗号分隔，例如 Vue、FastAPI" /></el-form-item>
      <el-button type="primary" native-type="submit" :loading="saving">保存</el-button>
    </el-form>
  </el-dialog>
  <el-dialog v-model="assignDialog" :title="`分配任务：${assigningTask?.title || ''}`" width="420px">
    <el-select v-model="selectedAssigneeId" placeholder="选择任务执行人" style="width: 100%">
      <el-option v-for="member in members.filter(item => item.user.is_active)" :key="member.user.id" :label="`${member.user.name}（${member.user.email}）`" :value="member.user.id" />
    </el-select>
    <template #footer><el-button @click="assignDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveAssignment">确认分配</el-button></template>
  </el-dialog>
  <el-dialog v-model="repositoryDialog" title="绑定公开 GitHub 仓库" width="520px">
    <p class="muted">填写仓库主页地址，例如 https://github.com/owner/repo。系统只读取公开仓库的信息；已有任务关联代码链接后不能更换或移除仓库。</p>
    <el-input v-model="repositoryUrl" placeholder="https://github.com/owner/repo" />
    <template #footer><el-button @click="repositoryDialog = false">取消</el-button><el-button type="primary" :loading="savingRepository" @click="saveRepository">保存仓库</el-button></template>
  </el-dialog>
  <el-dialog v-model="reviewDialog" :title="`PR 改动证据：${reviewedTask?.title || ''}`" width="780px">
    <p class="muted">项目负责人可读取公开 PR 改动并保存快照。只有再次主动点击生成 AI 建议、完成两次确认后，任务文字和补丁才会发送给 DeepSeek；验收决定仍由负责人作出。</p>
    <el-button v-if="isOwner && reviewedTask?.status === 'review'" type="primary" :loading="capturingReview" @click="captureReview">读取当前 PR 改动</el-button>
    <el-skeleton v-if="loadingReviews" :rows="3" animated />
    <el-empty v-else-if="!reviewSnapshots.length" description="还没有保存 PR 改动快照" />
    <el-collapse v-else style="margin-top: 16px">
      <el-collapse-item v-for="snapshot in reviewSnapshots" :key="snapshot.id" :name="snapshot.id">
        <template #title>
          PR #{{ snapshot.snapshot.pr.number }} · {{ snapshot.snapshot.pr.title }} · {{ formatBeijingTime(snapshot.created_at) }}
          <el-tag v-if="!snapshot.is_current" size="small" type="warning" style="margin-left: 8px">任务或代码已变化</el-tag>
        </template>
        <p>作者：{{ snapshot.snapshot.pr.author }} · 状态：{{ snapshot.snapshot.pr.state }} · SHA：{{ snapshot.snapshot.pr.head_sha.slice(0, 12) }}</p>
        <p class="muted">共 {{ snapshot.snapshot.pr.files.length }} 个改动文件；快照读取于 {{ formatBeijingTime(snapshot.snapshot.pr.fetched_at) }}。PR 后续可能继续变化。</p>
        <el-button v-if="isOwner && reviewedTask?.status === 'review' && snapshot.is_current" size="small" type="primary" :loading="generatingAdviceId === snapshot.id" :disabled="confirmingAdviceId !== null" @click="generateReviewAdvice(snapshot)">生成 AI 验收建议</el-button>
        <div v-for="item in reviewAdvice[snapshot.id] || []" :key="item.id" style="margin: 14px 0; padding: 14px; border-radius: 8px; background: var(--el-fill-color-light)">
          <strong>AI 建议 · {{ formatBeijingTime(item.created_at) }}</strong>
          <p class="muted">仅基于此快照中的任务条件和 PR 补丁，不代表测试通过或自动验收。</p>
          <p>{{ item.advice.summary }}</p>
          <div v-for="(finding, index) in item.advice.findings" :key="index" style="padding: 8px 0; border-top: 1px solid var(--el-border-color-lighter)">
            <el-tag size="small" :type="finding.assessment === 'supported' ? 'success' : 'warning'">{{ finding.assessment === 'supported' ? '有相关代码证据' : finding.assessment === 'manual_check' ? '需人工核实' : '证据不足' }}</el-tag>
            <strong style="margin-left: 8px">{{ finding.criterion }}</strong>
            <p>{{ finding.explanation }}</p>
            <p v-if="finding.evidence_paths.length" class="muted">相关文件：{{ finding.evidence_paths.join('、') }}</p>
          </div>
          <div v-if="item.advice.manual_tests.length">
            <strong>建议人工检查</strong>
            <ul><li v-for="(test, index) in item.advice.manual_tests" :key="index">{{ test }}</li></ul>
          </div>
        </div>
        <div v-for="file in snapshot.snapshot.pr.files" :key="file.path" style="padding: 12px 0; border-top: 1px solid var(--el-border-color-lighter)">
          <strong>{{ file.path }}</strong> <span class="muted">{{ file.status }} · +{{ file.additions }} / -{{ file.deletions }}</span>
          <pre v-if="file.patch" style="overflow: auto; max-height: 300px; padding: 12px; background: var(--el-fill-color-light); white-space: pre">{{ file.patch }}</pre>
          <p v-else class="muted">GitHub 未提供文本补丁，请人工打开 PR 检查此文件。</p>
        </div>
      </el-collapse-item>
    </el-collapse>
  </el-dialog>
  <el-dialog v-model="checklistDialog" :title="`开发清单：${checklistTask?.title || ''}`" width="640px">
    <p class="muted">AI 根据任务描述和验收条件给出建议。勾选表示执行人自行确认完成，验收仍由项目负责人决定。</p>
    <el-empty v-if="!checklistItems.length" description="暂无清单，可生成 AI 建议" />
    <div v-for="(item, index) in checklistItems" :key="index" style="padding: 12px 0; border-top: 1px solid var(--el-border-color-lighter)">
      <el-checkbox v-model="item.checked" :disabled="checklistTask?.assignee_id !== auth.user?.id || checklistTask?.status !== 'in_progress'">
        {{ item.title }}
      </el-checkbox>
      <el-tag size="small" type="info" style="margin-left: 8px">{{ item.kind === 'test' ? '测试' : '实现' }}</el-tag>
      <p class="muted" style="margin: 4px 0 0 24px">{{ item.detail }}</p>
    </div>
    <template #footer>
      <el-button v-if="(isOwner || checklistTask?.assignee_id === auth.user?.id) && checklistTask?.status !== 'review' && checklistTask?.status !== 'done'" :loading="generatingChecklist" @click="generateChecklist">{{ checklistItems.length ? '重新生成' : 'AI 生成清单' }}</el-button>
      <el-button v-if="checklistTask?.assignee_id === auth.user?.id && checklistTask?.status === 'in_progress' && checklistItems.length" type="primary" :loading="savingChecklist" @click="saveChecklist">保存勾选</el-button>
    </template>
  </el-dialog>
  <el-dialog v-model="submitDialog" :title="`提交成果：${submittingTask?.title || ''}`" width="560px">
    <p v-if="project?.github_repo_url" class="muted">代码链接须是当前项目仓库的提交详情或 PR；提交时会从 GitHub 核验并保存摘要。</p>
    <p v-else class="muted">当前项目未绑定仓库，代码链接只会作为手动成果记录，不会核验。</p>
    <el-form label-position="top" @submit.prevent="submit">
      <el-form-item label="成果说明"><el-input v-model="submitForm.note" type="textarea" placeholder="说明实现内容" /></el-form-item>
      <el-form-item label="成果链接"><el-input v-model="submitForm.url" type="url" placeholder="可选，例如演示页面或文档 URL" /></el-form-item>
      <el-form-item label="代码或 PR 链接"><el-input v-model="submitForm.code_url" type="url" placeholder="可选，例如 GitHub 提交或 PR URL" /></el-form-item>
      <el-form-item label="测试记录链接"><el-input v-model="submitForm.test_url" type="url" placeholder="可选，例如 CI 运行结果 URL" /></el-form-item>
      <el-form-item label="测试说明"><el-input v-model="submitForm.test_note" type="textarea" maxlength="3000" show-word-limit placeholder="记录执行的测试及结果，勿把未经验证的测试写成通过" /></el-form-item>
      <el-button type="primary" native-type="submit" :loading="saving">提交验收</el-button>
    </el-form>
  </el-dialog>
  <el-dialog v-model="weightDialog" :title="`任务权重：${weightedTask?.title || ''}`" width="560px">
    <p class="muted">按四项指标计算规划分值。建议仅供参考，项目负责人确认后才会保存。</p>
    <el-form label-position="top">
      <el-row :gutter="16">
        <el-col :span="12"><el-form-item label="技术复杂度（1–5）"><el-input-number v-model="weightForm.complexity" :min="1" :max="5" @change="invalidateWeightSuggestion" /></el-form-item></el-col>
        <el-col :span="12"><el-form-item label="预计工作量（小时）"><el-input-number v-model="weightForm.estimated_hours" :min="1" :max="80" @change="invalidateWeightSuggestion" /></el-form-item></el-col>
        <el-col :span="12"><el-form-item label="项目重要性（1–5）"><el-input-number v-model="weightForm.importance" :min="1" :max="5" @change="invalidateWeightSuggestion" /></el-form-item></el-col>
        <el-col :span="12"><el-form-item label="实现风险（1–5）"><el-input-number v-model="weightForm.risk" :min="1" :max="5" @change="invalidateWeightSuggestion" /></el-form-item></el-col>
      </el-row>
      <el-button :loading="suggestingWeight" @click="suggestWeight">计算建议分值</el-button>
      <div v-if="weightSuggestion" style="margin-top: 18px; padding: 16px; border-radius: 10px; background: #f3f7fd">
        <strong>建议权重：{{ weightSuggestion.suggested_score }}/100</strong>
        <p style="line-height: 1.7; margin-bottom: 0">{{ weightSuggestion.rationale }}</p>
      </div>
      <template v-if="weightSuggestion">
        <el-form-item label="项目负责人确认分值（1–100）" style="margin-top: 18px"><el-input-number v-model="weightForm.confirmed_score" :min="1" :max="100" /></el-form-item>
        <el-form-item v-if="weightForm.confirmed_score !== weightSuggestion.suggested_score" label="调整原因（必填）"><el-input v-model="weightForm.adjustment_reason" type="textarea" maxlength="500" show-word-limit placeholder="说明与建议分值不同的原因" /></el-form-item>
      </template>
    </el-form>
    <template #footer><el-button @click="weightDialog = false">取消</el-button><el-button type="primary" :disabled="!weightSuggestion" :loading="savingWeight" @click="confirmWeight">确认并保存</el-button></template>
  </el-dialog>
  <el-dialog v-model="dependencyDialog" :title="`任务依赖：${dependencyTask?.title || ''}`" width="480px">
    <p class="muted">选择此任务开始前需要完成的任务。系统会检查循环依赖。</p>
    <el-select v-model="selectedDependencies" multiple clearable placeholder="选择前置任务" style="width: 100%">
      <el-option v-for="task in tasks.filter(item => item.id !== dependencyTask?.id)" :key="task.id" :label="task.title" :value="task.id" />
    </el-select>
    <template #footer><el-button @click="dependencyDialog = false">取消</el-button><el-button type="primary" :loading="savingDependencies" @click="saveDependencies">保存依赖</el-button></template>
  </el-dialog>
  <el-dialog v-model="transferDialog" title="转让项目负责人" width="420px">
    <p class="muted">转让后你将成为普通成员，可选择退出项目。</p>
    <el-select v-model="newOwnerId" placeholder="选择接任成员" style="width: 100%">
      <el-option v-for="member in members.filter(item => item.user.is_active && item.user.id !== auth.user?.id)" :key="member.user.id" :label="`${member.user.name}（${member.user.email}）`" :value="member.user.id" />
    </el-select>
    <template #footer><el-button @click="transferDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="transferOwner">确认转让</el-button></template>
  </el-dialog>
  <el-dialog v-model="inviteDialog" title="邀请已注册用户" width="420px">
    <el-input v-model="inviteEmail" type="email" placeholder="成员邮箱" />
    <template #footer><el-button @click="inviteDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="invite">邀请</el-button></template>
  </el-dialog>
  <el-dialog v-model="eventDialog" title="任务记录" width="520px">
    <el-timeline><el-timeline-item v-for="event in events" :key="event.id" :timestamp="`${formatBeijingTime(event.created_at)} 北京时间`">
      {{ event.action }} · {{ event.actor_name }}<div v-if="event.note" class="muted">{{ event.note }}</div>
    </el-timeline-item></el-timeline>
  </el-dialog>
</template>
