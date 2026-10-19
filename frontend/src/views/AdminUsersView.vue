<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi } from '../api/admin'
import { useAuthStore } from '../stores/auth'
import type { AdminUser } from '../types'

const auth = useAuthStore()
const users = ref<AdminUser[]>([])
const search = ref('')
const filteredUsers = computed(() => {
  const term = search.value.trim().toLocaleLowerCase()
  if (!term) return users.value
  return users.value.filter(user =>
    user.name.toLocaleLowerCase().includes(term) || user.email.toLocaleLowerCase().includes(term),
  )
})
const createDialog = ref(false)
const saving = ref(false)
const deactivateDialog = ref(false)
const selectedUser = ref<AdminUser | null>(null)
const successorId = ref<number | null>(null)
const form = reactive({ name: '', email: '', password: '', is_admin: false })
async function load() {
  try { users.value = await adminApi.users() }
  catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载用户失败') }
}
async function createUser() {
  saving.value = true
  try {
    await adminApi.create(form)
    createDialog.value = false
    Object.assign(form, { name: '', email: '', password: '', is_admin: false })
    await load()
    ElMessage.success('用户已创建')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '创建失败') }
  finally { saving.value = false }
}
function openDeactivate(user: AdminUser) {
  selectedUser.value = user
  successorId.value = null
  deactivateDialog.value = true
}
async function deactivate() {
  if (!selectedUser.value) return
  saving.value = true
  try {
    await adminApi.deactivate(selectedUser.value.id, successorId.value)
    deactivateDialog.value = false
    await load()
    ElMessage.success('账号已停用')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '停用失败') }
  finally { saving.value = false }
}
async function restore(user: AdminUser) {
  try { await adminApi.restore(user.id); await load() }
  catch (error) { ElMessage.error(error instanceof Error ? error.message : '恢复失败') }
}
onMounted(load)
</script>

<template>
  <div class="page-header">
    <div><h1>用户管理</h1><p>搜索用户，进入详情查看其项目创建与删除记录</p></div>
    <el-button type="primary" @click="createDialog = true">新增用户</el-button>
  </div>
  <el-input v-model="search" clearable placeholder="搜索姓名或邮箱" style="max-width: 380px; margin-bottom: 18px" />
  <el-table :data="filteredUsers" stripe>
    <el-table-column prop="name" label="姓名" />
    <el-table-column prop="email" label="邮箱" min-width="220" />
    <el-table-column label="角色" width="120"><template #default="scope"><el-tag v-if="scope.row.is_admin" type="danger">管理员</el-tag><span v-else>用户</span></template></el-table-column>
    <el-table-column label="状态" width="100"><template #default="scope"><el-tag :type="scope.row.is_active ? 'success' : 'info'">{{ scope.row.is_active ? '正常' : '已停用' }}</el-tag></template></el-table-column>
    <el-table-column label="项目记录" width="130"><template #default="scope">
      <el-badge :value="scope.row.unread_project_activity_count" :hidden="scope.row.unread_project_activity_count === 0">
        <router-link :to="`/admin/users/${scope.row.id}`">查看 {{ scope.row.project_activity_count }} 条</router-link>
      </el-badge>
    </template></el-table-column>
    <el-table-column label="操作" width="130"><template #default="scope">
      <el-button v-if="scope.row.is_active && scope.row.id !== auth.user?.id" size="small" type="danger" text @click="openDeactivate(scope.row)">停用</el-button>
      <el-button v-if="!scope.row.is_active" size="small" type="primary" text @click="restore(scope.row)">恢复</el-button>
    </template></el-table-column>
  </el-table>
  <el-dialog v-model="createDialog" title="新增用户" width="480px">
    <el-form label-position="top" @submit.prevent="createUser">
      <el-form-item label="姓名"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="邮箱"><el-input v-model="form.email" type="email" /></el-form-item>
      <el-form-item label="初始密码（至少 8 位）"><el-input v-model="form.password" type="password" show-password /></el-form-item>
      <el-form-item><el-checkbox v-model="form.is_admin">设为系统管理员</el-checkbox></el-form-item>
      <el-button type="primary" native-type="submit" :loading="saving">创建</el-button>
    </el-form>
  </el-dialog>
  <el-dialog v-model="deactivateDialog" title="停用用户" width="480px">
    <p>停用 {{ selectedUser?.name }} 后，该账号无法登录，历史记录仍会保留。</p>
    <p class="muted">如果此人是项目负责人，请指定接任项目负责人；其负责的全部项目将转交给该用户。</p>
    <el-select v-model="successorId" clearable placeholder="接任项目负责人（负责项目时必填）" style="width: 100%">
      <el-option v-for="user in users.filter(item => item.is_active && item.id !== selectedUser?.id)" :key="user.id" :label="`${user.name} (${user.email})`" :value="user.id" />
    </el-select>
    <template #footer><el-button @click="deactivateDialog = false">取消</el-button><el-button type="danger" :loading="saving" @click="deactivate">确认停用</el-button></template>
  </el-dialog>
</template>
