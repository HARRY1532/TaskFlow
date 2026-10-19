<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { profileApi } from '../api/profile'
import { baseUrl } from '../api/client'
import { useAuthStore } from '../stores/auth'
import { skillsApi } from '../api/skills'
import type { Skill, SkillCategory } from '../types'

const auth = useAuthStore()
const name = ref(auth.user?.name || '')
const saving = ref(false)
const uploading = ref(false)
const changingPassword = ref(false)
const currentPasswordReady = ref(false)
const passwords = reactive({ current: '', next: '' })
const input = ref<HTMLInputElement | null>(null)
const avatarVersion = ref(0)
const avatarUrl = computed(() => auth.user?.avatar_url ? `${new URL(auth.user.avatar_url, baseUrl).href}?v=${avatarVersion.value}` : undefined)
const skillSaving = ref(false)
const skillLoading = ref(true)
const skillForm = reactive({ weekly_hours: 0, learning_goal: '', skills: [] as Skill[] })
const categories: { value: SkillCategory; label: string }[] = [
  { value: 'language', label: '编程语言' }, { value: 'frontend', label: '前端' },
  { value: 'backend', label: '后端' }, { value: 'database', label: '数据库' },
  { value: 'testing', label: '测试' }, { value: 'other', label: '其他' },
]
const skillCount = computed(() => skillForm.skills.filter(skill => skill.name.trim()).length)
async function loadSkills() {
  try {
    const profile = await skillsApi.mine()
    skillForm.weekly_hours = profile.weekly_hours
    skillForm.learning_goal = profile.learning_goal
    skillForm.skills = profile.skills
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载技能画像失败') }
  finally { skillLoading.value = false }
}
function addSkill() {
  if (skillForm.skills.length < 20) skillForm.skills.push({ category: 'language', name: '', level: 3 })
}
async function saveSkills() {
  const skills = skillForm.skills.map(skill => ({ ...skill, name: skill.name.trim() }))
  if (skills.some(skill => !skill.name)) { ElMessage.error('请填写每项技能的名称'); return }
  const keys = skills.map(skill => `${skill.category}:${skill.name.toLocaleLowerCase()}`)
  if (new Set(keys).size !== keys.length) { ElMessage.error('同一类别中不能重复填写技能'); return }
  skillSaving.value = true
  try {
    const saved = await skillsApi.save({ weekly_hours: skillForm.weekly_hours, learning_goal: skillForm.learning_goal, skills })
    skillForm.skills = saved.skills
    ElMessage.success('技能画像已保存')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '保存技能画像失败') }
  finally { skillSaving.value = false }
}
onMounted(loadSkills)
async function save() {
  saving.value = true
  try { auth.setUser(await profileApi.update(name.value)); ElMessage.success('个人信息已更新') }
  catch (error) { ElMessage.error(error instanceof Error ? error.message : '保存失败') }
  finally { saving.value = false }
}
async function onFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  if (file.size > 2 * 1024 * 1024) { ElMessage.error('图片不能超过 2 MB'); return }
  uploading.value = true
  try { auth.setUser(await profileApi.uploadAvatar(file)); avatarVersion.value++; ElMessage.success('头像已更新') }
  catch (error) { ElMessage.error(error instanceof Error ? error.message : '上传失败') }
  finally { uploading.value = false; if (input.value) input.value.value = '' }
}
async function changePassword() {
  if (!passwords.current) { ElMessage.error('请输入当前密码'); return }
  if (passwords.next.length < 8) { ElMessage.error('新密码至少需要 8 位'); return }
  changingPassword.value = true
  try {
    await profileApi.changePassword(passwords.current, passwords.next)
    passwords.current = ''
    passwords.next = ''
    currentPasswordReady.value = false
    ElMessage.success('密码已更新')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '修改密码失败') }
  finally { changingPassword.value = false }
}
function enableCurrentPasswordInput(event: FocusEvent) {
  if (currentPasswordReady.value) return
  passwords.current = ''
  ;(event.target as HTMLInputElement).value = ''
  currentPasswordReady.value = true
}
</script>

<template>
  <div class="profile-page">
    <header class="profile-hero">
      <div>
        <span class="profile-eyebrow">ACCOUNT · 个人中心</span>
        <h1>个人信息</h1>
        <p>维护个人资料与技能画像，让项目负责人更了解你的工作能力和时间安排。</p>
      </div>
      <div class="hero-mark" aria-hidden="true">TF</div>
    </header>

    <div class="profile-layout">
      <aside class="profile-sidebar">
        <section class="profile-card identity-card">
          <div class="avatar-wrap"><el-avatar :size="96" :src="avatarUrl">{{ auth.user?.name.slice(0, 1) }}</el-avatar></div>
          <h2>{{ auth.user?.name }}</h2>
          <p class="identity-email">{{ auth.user?.email }}</p>
          <el-tag :type="auth.user?.is_admin ? 'warning' : 'info'" effect="plain" round>{{ auth.user?.is_admin ? '系统管理员' : '项目成员' }}</el-tag>
          <input ref="input" type="file" accept="image/jpeg,image/png,image/webp" class="file-input" aria-label="选择头像照片" @change="onFile">
          <el-button class="upload-button" :loading="uploading" @click="input?.click()">更换头像</el-button>
          <p class="avatar-hint">支持 JPG、PNG、WebP，最大 2 MB</p>
        </section>
        <section class="profile-card snapshot-card">
          <p class="section-kicker">画像概览</p>
          <div class="snapshot-row"><span>已填写技能</span><strong>{{ skillCount }} <small>项</small></strong></div>
          <div class="snapshot-row"><span>每周可投入</span><strong>{{ skillForm.weekly_hours }} <small>小时</small></strong></div>
          <p class="snapshot-note">画像由你本人维护，项目负责人可在项目中查看。</p>
        </section>
      </aside>

      <div class="profile-content">
        <section class="profile-card content-card">
          <div class="section-heading"><div><p class="section-kicker">01 / 基本资料</p><h2>关于你</h2><p>姓名会显示在项目成员与任务记录中。</p></div></div>
          <el-form label-position="top" @submit.prevent="save">
            <div class="basic-fields">
              <el-form-item label="姓名"><el-input v-model="name" maxlength="100" placeholder="请输入姓名" /></el-form-item>
              <el-form-item label="邮箱"><el-input :model-value="auth.user?.email" disabled /></el-form-item>
            </div>
            <div class="section-actions"><span>邮箱用于登录，暂不支持在此修改。</span><el-button type="primary" native-type="submit" :loading="saving">保存基本资料</el-button></div>
          </el-form>
        </section>

        <section v-loading="skillLoading" class="profile-card content-card skills-card">
          <div class="section-heading"><div><p class="section-kicker">02 / 工程能力</p><h2>技能画像</h2><p>填写真实水平，帮助项目负责人了解你适合的任务。</p></div><span class="skill-counter">{{ skillCount }} / 20 项</span></div>
          <el-form label-position="top" @submit.prevent="saveSkills">
            <div class="skill-meta-fields">
              <el-form-item label="每周可投入时间"><el-input-number v-model="skillForm.weekly_hours" :min="0" :max="80" /><span class="field-help">小时 / 周</span></el-form-item>
              <el-form-item label="学习目标"><el-input v-model="skillForm.learning_goal" type="textarea" :rows="2" maxlength="1000" show-word-limit placeholder="例如：希望在本项目中练习后端接口设计" /></el-form-item>
            </div>
            <div class="skills-heading"><div><h3>技能清单</h3><p>熟练度从 1（入门）到 5（熟练）</p></div><el-button :disabled="skillForm.skills.length >= 20" @click="addSkill">＋ 添加技能</el-button></div>
            <div v-if="!skillForm.skills.length" class="skills-empty">还没有填写技能。点击“添加技能”开始完善画像。</div>
            <div v-for="(skill, index) in skillForm.skills" :key="index" class="skill-row">
              <span class="skill-index">{{ String(index + 1).padStart(2, '0') }}</span>
              <el-select v-model="skill.category" class="skill-category" aria-label="技能类别" placeholder="类别"><el-option v-for="category in categories" :key="category.value" :label="category.label" :value="category.value" /></el-select>
              <el-input v-model="skill.name" class="skill-name" maxlength="60" aria-label="技能名称" placeholder="例如 Python、Vue 3" />
              <el-select v-model="skill.level" class="skill-level" aria-label="熟练度" placeholder="等级"><el-option v-for="level in 5" :key="level" :label="`${level} 级`" :value="level" /></el-select>
              <el-button class="skill-remove" type="danger" text aria-label="移除技能" @click="skillForm.skills.splice(index, 1)">移除</el-button>
            </div>
            <div class="section-actions"><span>修改后记得保存，项目负责人才能看到最新画像。</span><el-button type="primary" native-type="submit" :loading="skillSaving" :disabled="skillLoading">保存技能画像</el-button></div>
          </el-form>
        </section>

        <section class="profile-card content-card security-card">
          <div class="section-heading"><div><p class="section-kicker">03 / 账号安全</p><h2>修改密码</h2><p>使用至少 8 位的新密码保护账号。</p></div></div>
          <el-form label-position="top" @submit.prevent="changePassword">
            <div class="basic-fields">
              <el-form-item label="当前密码"><el-input v-model="passwords.current" type="password" autocomplete="off" :readonly="!currentPasswordReady" placeholder="请手动输入当前密码" @focus="enableCurrentPasswordInput" /></el-form-item>
              <el-form-item label="新密码"><el-input v-model="passwords.next" type="password" autocomplete="new-password" show-password placeholder="至少 8 位" /></el-form-item>
            </div>
            <div class="section-actions"><span>修改后，下次登录请使用新密码。</span><el-button native-type="submit" :loading="changingPassword">更新密码</el-button></div>
          </el-form>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.profile-page { max-width: 1120px; margin: 0 auto; }
.profile-hero { position: relative; overflow: hidden; display: flex; justify-content: space-between; align-items: center; min-height: 194px; padding: 34px 42px; border-radius: 20px; color: #fff; background: linear-gradient(115deg, #172d51 0%, #244879 60%, #3969a1 100%); margin-bottom: 24px; }
.profile-hero::after { content: ''; position: absolute; right: 130px; top: -116px; width: 340px; height: 340px; border: 1px solid #ffffff27; border-radius: 50%; box-shadow: 0 0 0 42px #ffffff0b, 0 0 0 84px #ffffff08; }
.profile-hero > div:first-child { position: relative; z-index: 1; }
.profile-eyebrow { color: #c3d7f4; font-size: 11px; font-weight: 700; letter-spacing: .16em; }
.profile-hero h1 { margin: 14px 0 10px; font-size: 32px; letter-spacing: -.02em; }
.profile-hero p { max-width: 600px; margin: 0; color: #d5e3f7; line-height: 1.7; }
.hero-mark { position: relative; z-index: 1; display: grid; place-items: center; width: 86px; height: 86px; flex: none; border: 1px solid #ffffff57; border-radius: 22px; color: #ffffffd9; font-size: 26px; font-weight: 800; letter-spacing: -.05em; transform: rotate(-9deg); }
.profile-layout { display: grid; grid-template-columns: 290px minmax(0, 1fr); align-items: start; gap: 22px; }
.profile-sidebar, .profile-content { display: grid; gap: 20px; min-width: 0; }
.profile-card { background: #fff; border: 1px solid #e4eaf2; border-radius: 18px; box-shadow: 0 10px 30px #1d355208; }
.identity-card { padding: 30px 22px 26px; text-align: center; }
.avatar-wrap { display: flex; justify-content: center; margin-bottom: 16px; }
.avatar-wrap :deep(.el-avatar) { border: 5px solid #edf4ff; background: #dce9fa; color: #315889; font-size: 36px; }
.identity-card h2 { margin: 0 0 5px; font-size: 20px; }
.identity-email { overflow-wrap: anywhere; margin: 0 0 14px; color: #74839a; font-size: 13px; }
.file-input { display: none; }
.upload-button { display: block; margin: 23px auto 0; width: 100%; }
.avatar-hint { margin: 12px 0 0; color: #91a0b4; font-size: 12px; }
.snapshot-card { padding: 23px 22px; }
.section-kicker { margin: 0 0 8px; color: #4778ba; font-size: 11px; font-weight: 800; letter-spacing: .14em; }
.snapshot-row { display: flex; justify-content: space-between; align-items: baseline; padding: 13px 0; border-bottom: 1px solid #edf1f6; color: #677a94; font-size: 13px; }
.snapshot-row strong { color: #263a56; font-size: 21px; }
.snapshot-row small { font-size: 12px; font-weight: 500; }
.snapshot-note { margin: 17px 0 0; color: #8695a9; font-size: 12px; line-height: 1.7; }
.content-card { padding: 27px 30px 24px; }
.section-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 18px; margin-bottom: 22px; }
.section-heading h2 { margin: 0 0 7px; color: #243754; font-size: 21px; }
.section-heading > div > p:last-child { margin: 0; color: #7e8da3; font-size: 13px; line-height: 1.6; }
.basic-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.profile-card :deep(.el-form-item__label) { color: #40536f; font-weight: 600; }
.profile-card :deep(.el-input__wrapper), .profile-card :deep(.el-select__wrapper), .profile-card :deep(.el-textarea__inner) { border-radius: 9px; }
.section-actions { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding-top: 19px; border-top: 1px solid #edf1f6; }
.section-actions span { color: #91a0b2; font-size: 12px; line-height: 1.5; }
.section-actions .el-button { min-width: 126px; }
.skill-counter { flex: none; padding: 6px 11px; border-radius: 20px; background: #eef4fc; color: #4b79b6; font-size: 12px; font-weight: 700; }
.skill-meta-fields { display: grid; grid-template-columns: 190px minmax(0, 1fr); gap: 20px; }
.skill-meta-fields :deep(.el-input-number) { width: 125px; }
.field-help { margin-left: 8px; color: #8998aa; font-size: 12px; }
.skills-heading { display: flex; justify-content: space-between; align-items: center; gap: 14px; margin: 6px 0 12px; }
.skills-heading h3 { margin: 0 0 4px; font-size: 15px; color: #2b3e5a; }
.skills-heading p { margin: 0; font-size: 12px; color: #91a0b2; }
.skills-empty { padding: 20px; margin-bottom: 16px; border: 1px dashed #d9e3f0; border-radius: 12px; background: #f9fbfe; color: #91a0b2; font-size: 13px; text-align: center; }
.skill-row { display: grid; grid-template-columns: 30px 116px minmax(120px, 1fr) 96px 48px; align-items: center; gap: 10px; padding: 10px 12px; margin-bottom: 9px; border: 1px solid #e8edf4; border-radius: 11px; background: #fbfcfe; }
.skill-index { color: #a4b1c1; font-size: 12px; font-weight: 700; }
.skill-row .el-select, .skill-row .el-input { width: 100%; }
.skill-row .el-button { padding: 0; }
.skills-card .section-actions { margin-top: 23px; }
@media (max-width: 900px) { .profile-layout { grid-template-columns: 1fr; } .profile-sidebar { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); } }
@media (max-width: 640px) { .profile-hero { min-height: 170px; padding: 28px 24px; } .profile-hero h1 { font-size: 28px; } .hero-mark { display: none; } .profile-sidebar { grid-template-columns: 1fr; } .content-card { padding: 22px 18px; } .basic-fields, .skill-meta-fields { grid-template-columns: 1fr; gap: 0; } .skill-row { grid-template-columns: 25px minmax(0, 1fr) 96px 40px; } .skill-category { grid-column: 2; grid-row: 1; } .skill-name { grid-column: 2 / 4; grid-row: 2; } .skill-level { grid-column: 3; grid-row: 1; } .skill-remove { grid-column: 4; grid-row: 1; } .section-actions { align-items: stretch; flex-direction: column; } .section-actions .el-button { width: 100%; margin-left: 0; } }
</style>
