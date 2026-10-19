<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const email = ref('')
const password = ref('')
const loading = ref(false)
const auth = useAuthStore()
const router = useRouter()
async function submit() {
  loading.value = true
  try { await auth.login(email.value, password.value); await router.push('/projects') }
  catch (error) { ElMessage.error(error instanceof Error ? error.message : '登录失败') }
  finally { loading.value = false }
}
</script>

<template>
  <section class="auth-card">
    <h1>登录 TaskFlow AI</h1>
    <el-form label-position="top" @submit.prevent="submit">
      <el-form-item label="邮箱"><el-input v-model="email" type="email" autocomplete="email" /></el-form-item>
      <el-form-item label="密码"><el-input v-model="password" type="password" autocomplete="current-password" show-password /></el-form-item>
      <el-button type="primary" native-type="submit" :loading="loading">登录</el-button>
    </el-form>
    <p>还没有账号？<router-link to="/register">注册</router-link></p>
  </section>
</template>
