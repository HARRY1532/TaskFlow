import { api, json } from './client'
import type { TaskDependencies } from '../types'

export const dependenciesApi = {
  list: (projectId: number) => api<TaskDependencies[]>(`/projects/${projectId}/dependencies`),
  save: (projectId: number, taskId: number, depends_on_ids: number[]) =>
    api<TaskDependencies>(`/projects/${projectId}/tasks/${taskId}/dependencies`, json('PUT', { depends_on_ids })),
}
