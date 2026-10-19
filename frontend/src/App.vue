<script setup lang="ts">
import { onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { useActivitiesStore } from './stores/activities'
import { baseUrl } from './api/client'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const activities = useActivitiesStore()
const avatarUrl = (path: string | null) => path ? new URL(path, baseUrl).href : undefined
function logout() { auth.logout(); router.push('/login') }
watch(() => [auth.user?.is_admin, route.fullPath], () => {
  if (auth.user?.is_admin) activities.refresh().catch(() => activities.clear())
  else activities.clear()
}, { immediate: true })
let activityTimer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  activityTimer = setInterval(() => {
    if (auth.user?.is_admin) activities.refresh().catch(() => activities.clear())
  }, 30_000)
})
onUnmounted(() => { if (activityTimer) clearInterval(activityTimer) })
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <router-link class="brand" to="/projects">TaskFlow <span>AI</span></router-link>
      <nav v-if="auth.user">
        <router-link to="/projects">项目</router-link>
        <router-link to="/invitations">邀请</router-link>
        <router-link v-if="auth.user.is_admin" to="/admin/users">
          <el-badge :value="activities.unreadCount" :hidden="activities.unreadCount === 0">用户管理</el-badge>
        </router-link>
        <router-link to="/profile" class="profile-link">
          <el-avatar :size="30" :src="avatarUrl(auth.user.avatar_url)">{{ auth.user.name.slice(0, 1) }}</el-avatar>
          <span>{{ auth.user.name }}</span>
        </router-link>
        <el-button text @click="logout">退出登录</el-button>
      </nav>
    </header>
    <main><router-view /></main>
  </div>
</template>
