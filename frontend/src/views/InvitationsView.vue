<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { invitationApi } from '../api/invitation'
import { formatBeijingTime } from '../utils/date'
import type { Invitation } from '../types'

const invitations = ref<Invitation[]>([])
const busy = ref<number | null>(null)
const statusLabel: Record<Invitation['status'], string> = {
  pending: '待处理', accepted: '已接受', declined: '已拒绝', cancelled: '已撤销',
}
async function load() {
  try { invitations.value = await invitationApi.list() }
  catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载邀请失败') }
}
async function respond(invitation: Invitation, accept: boolean) {
  busy.value = invitation.id
  try {
    if (accept) await invitationApi.accept(invitation.id)
    else await invitationApi.decline(invitation.id)
    ElMessage.success(accept ? '已加入项目' : '已拒绝邀请')
    await load()
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '处理失败') }
  finally { busy.value = null }
}
onMounted(load)
</script>

<template>
  <div class="page-header"><div><h1>项目邀请</h1><p>接受邀请后才会成为项目成员</p></div></div>
  <el-empty v-if="!invitations.length" description="暂无项目邀请" />
  <el-card v-for="invitation in invitations" :key="invitation.id" style="margin-bottom: 12px">
    <div class="page-header" style="margin-bottom: 0">
      <div>
        <h3 style="margin: 0 0 6px">{{ invitation.project_name }}</h3>
        <span class="muted">{{ invitation.inviter_name }} 邀请你加入 · {{ formatBeijingTime(invitation.created_at) }} 北京时间</span>
      </div>
      <div v-if="invitation.status === 'pending'">
        <el-button :loading="busy === invitation.id" @click="respond(invitation, false)">拒绝</el-button>
        <el-button type="primary" :loading="busy === invitation.id" @click="respond(invitation, true)">接受并加入</el-button>
      </div>
      <el-tag v-else>{{ statusLabel[invitation.status] }}</el-tag>
    </div>
  </el-card>
</template>
