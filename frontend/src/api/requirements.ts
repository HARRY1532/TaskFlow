import { api, json } from './client'
import type { Requirement, RequirementInput, RequirementMatchSuggestion } from '../types'

const path = (projectId: number) => `/projects/${projectId}/requirements`

export const requirementsApi = {
  list: (projectId: number) => api<Requirement[]>(path(projectId)),
  create: (projectId: number, data: RequirementInput) => api<Requirement>(path(projectId), json('POST', data)),
  update: (projectId: number, id: number, data: RequirementInput) => api<Requirement>(`${path(projectId)}/${id}`, json('PUT', data)),
  suggestTasks: (projectId: number, id: number) => api<RequirementMatchSuggestion>(`${path(projectId)}/${id}/recommendations`, { method: 'POST' }),
  linkTasks: (projectId: number, id: number, taskIds: number[], signature?: string) => api<Requirement>(`${path(projectId)}/${id}/tasks`, json('PUT', { task_ids: taskIds, expected_signature: signature || null })),
  remove: (projectId: number, id: number) => api<void>(`${path(projectId)}/${id}`, { method: 'DELETE' }),
}
