<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { adminApi } from '../api/admin'
import { projectActivityApi } from '../api/projectActivity'
import { useActivitiesStore } from '../stores/activities'
import { formatBeijingTime } from '../utils/date'
import type { AdminUser, ProjectActivity } from '../types'

const route = useRoute()
const user = ref<AdminUser | null>(null)
const activities = ref<ProjectActivity[]>([])
const activityStore = useActivitiesStore()
async function load() {
  try {
    const id = Number(route.params.id)
    ;[user.value, activities.value] = await Promise.all([
      adminApi.user(id), projectActivityApi.byUser(id),
    ])
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载用户详情失败') }
}
async function markRead(activity: ProjectActivity) {
  try {
    const updated = await projectActivityApi.markRead(activity.id)
    activity.is_read = updated.is_read
    if (user.value && user.value.unread_project_activity_count > 0) user.value.unread_project_activity_count--
    await activityStore.refresh()
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '操作失败') }
}
watch(() => route.params.id, load, { immediate: true })
</script>

<template>
  <div v-if="user">
    <div class="page-header">
      <div><router-link to="/admin/users">← 用户管理</router-link><h1>{{ user.name }}</h1><p>{{ user.email }} · {{ user.is_active ? '正常' : '已停用' }}</p></div>
    </div>
    <el-card style="margin-bottom: 18px">
      <strong>项目操作记录</strong>
      <p class="muted">共 {{ user.project_activity_count }} 条，未读 {{ user.unread_project_activity_count }} 条。时间均为北京时间（UTC+8）。</p>
    </el-card>
    <el-empty v-if="!activities.length" description="该用户暂无项目创建或删除记录" />
    <el-card v-for="activity in activities" :key="activity.id" style="margin-bottom: 12px">
      <div class="page-header" style="margin-bottom: 0">
        <div>
          <div><el-tag v-if="!activity.is_read" type="danger" size="small">未读</el-tag> {{ activity.action === 'created' ? '创建项目' : '删除项目' }}“{{ activity.project_name }}”</div>
          <small class="muted">{{ formatBeijingTime(activity.created_at) }} 北京时间</small>
        </div>
        <el-button v-if="!activity.is_read" size="small" @click="markRead(activity)">标为已读</el-button>
      </div>
    </el-card>
  </div>
</template>
