import { api, json } from './client'
import type { ChecklistItem, Task, TaskEvent, TaskReviewAdvice, TaskReviewSnapshot } from '../types'

const path = (projectId: number) => `/projects/${projectId}/tasks`
export const taskApi = {
  list: (projectId: number) => api<Task[]>(path(projectId)),
  create: (projectId: number, data: object) => api<Task>(path(projectId), json('POST', data)),
  update: (projectId: number, taskId: number, data: object) =>
    api<Task>(`${path(projectId)}/${taskId}`, json('PATCH', data)),
  remove: (projectId: number, taskId: number) =>
    api<void>(`${path(projectId)}/${taskId}`, { method: 'DELETE' }),
  start: (projectId: number, taskId: number) =>
    api<Task>(`${path(projectId)}/${taskId}/start`, { method: 'POST' }),
  submit: (projectId: number, taskId: number, data: { note: string; url: string | null; code_url: string | null; test_url: string | null; test_note: string }) =>
    api<Task>(`${path(projectId)}/${taskId}/submit`, json('POST', data)),
  generateChecklist: (projectId: number, taskId: number) =>
    api<ChecklistItem[]>(`${path(projectId)}/${taskId}/development-checklist/generate`, { method: 'POST' }),
  saveChecklist: (projectId: number, taskId: number, items: ChecklistItem[]) =>
    api<ChecklistItem[]>(`${path(projectId)}/${taskId}/development-checklist`, json('PUT', { items })),
  refreshCodeEvidence: (projectId: number, taskId: number) =>
    api<Task>(`${path(projectId)}/${taskId}/code-evidence/refresh`, { method: 'POST' }),
  reviewSnapshots: (projectId: number, taskId: number) =>
    api<TaskReviewSnapshot[]>(`${path(projectId)}/${taskId}/reviews`),
  captureReviewSnapshot: (projectId: number, taskId: number) =>
    api<TaskReviewSnapshot>(`${path(projectId)}/${taskId}/reviews`, { method: 'POST' }),
  reviewAdvice: (projectId: number, taskId: number, snapshotId: number) =>
    api<TaskReviewAdvice[]>(`${path(projectId)}/${taskId}/reviews/${snapshotId}/advice`),
  generateReviewAdvice: (projectId: number, taskId: number, snapshotId: number) =>
    api<TaskReviewAdvice>(`${path(projectId)}/${taskId}/reviews/${snapshotId}/advice`,
      json('POST', { acknowledged_risk: true, confirmed_send: true, confirmation_text: '发送至 DeepSeek' })),
  accept: (projectId: number, taskId: number, note: string) =>
    api<Task>(`${path(projectId)}/${taskId}/accept`, json('POST', { note })),
  reject: (projectId: number, taskId: number, note: string) =>
    api<Task>(`${path(projectId)}/${taskId}/reject`, json('POST', { note })),
  events: (projectId: number, taskId: number) =>
    api<TaskEvent[]>(`${path(projectId)}/${taskId}/events`),
}
