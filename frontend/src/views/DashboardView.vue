<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { projectApi } from '../api/project'
import type { Project } from '../types'

const projects = ref<Project[]>([])
const dialog = ref(false)
const saving = ref(false)
const form = reactive({ name: '', goal: '', requirements: '', tech_stack: '' })
const router = useRouter()
async function load() {
  try { projects.value = await projectApi.list() }
  catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载失败') }
}
async function create() {
  form.name = form.name.trim()
  if (!form.name) { ElMessage.error('项目名称必须填写实际内容'); return }
  saving.value = true
  try {
    const project = await projectApi.create(form)
    dialog.value = false
    await router.push(`/projects/${project.id}`)
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '创建失败') }
  finally { saving.value = false }
}
onMounted(load)
</script>

<template>
  <div class="page-header">
    <div><h1>我的项目</h1><p>管理课程项目与小组任务</p></div>
    <el-button type="primary" @click="dialog = true">创建项目</el-button>
  </div>
  <el-empty v-if="!projects.length" description="还没有项目，创建第一个课程项目吧" />
  <div class="project-grid">
    <router-link v-for="project in projects" :key="project.id" class="project-card" :to="`/projects/${project.id}`">
      <h3>{{ project.name }}</h3><p>{{ project.goal || '暂无项目目标' }}</p>
      <small>{{ project.tech_stack || '尚未填写技术栈' }}</small>
    </router-link>
  </div>
  <el-dialog v-model="dialog" title="创建项目" width="500px">
    <el-form label-position="top" @submit.prevent="create">
      <el-form-item label="项目名称"><el-input v-model="form.name" maxlength="120" /></el-form-item>
      <el-form-item label="项目目标"><el-input v-model="form.goal" type="textarea" :rows="3" /></el-form-item>
      <el-form-item label="详细需求（可稍后补充）"><el-input v-model="form.requirements" type="textarea" :rows="4" maxlength="10000" /></el-form-item>
      <el-form-item label="技术栈"><el-input v-model="form.tech_stack" placeholder="例如 Vue 3、FastAPI" /></el-form-item>
      <el-button type="primary" native-type="submit" :loading="saving">创建</el-button>
    </el-form>
  </el-dialog>
</template>
