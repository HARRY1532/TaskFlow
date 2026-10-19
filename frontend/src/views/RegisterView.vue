<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authApi } from '../api/auth'
import { useAuthStore } from '../stores/auth'

const form = reactive({ name: '', email: '', password: '' })
const loading = ref(false)
const router = useRouter()
const auth = useAuthStore()
async function submit() {
  loading.value = true
  try {
    await authApi.register(form)
    await auth.login(form.email, form.password)
    await router.push('/projects')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '注册失败') }
  finally { loading.value = false }
}
</script>

<template>
  <section class="auth-card">
    <h1>创建账号</h1>
    <el-form label-position="top" @submit.prevent="submit">
      <el-form-item label="姓名"><el-input v-model="form.name" maxlength="100" /></el-form-item>
      <el-form-item label="邮箱"><el-input v-model="form.email" type="email" autocomplete="email" /></el-form-item>
      <el-form-item label="密码（至少 8 位）"><el-input v-model="form.password" type="password" autocomplete="new-password" show-password /></el-form-item>
      <el-button type="primary" native-type="submit" :loading="loading">注册</el-button>
    </el-form>
    <p>已有账号？<router-link to="/login">登录</router-link></p>
  </section>
</template>
