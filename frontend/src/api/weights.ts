import { api, json } from './client'
import type { TaskWeight, WeightFactors, WeightSuggestion } from '../types'

export const weightsApi = {
  list: (projectId: number) => api<TaskWeight[]>(`/projects/${projectId}/weights`),
  suggest: (projectId: number, taskId: number, factors: WeightFactors) =>
    api<WeightSuggestion>(`/projects/${projectId}/tasks/${taskId}/weight/suggestion`, json('POST', factors)),
  confirm: (projectId: number, taskId: number, data: WeightFactors & { confirmed_score: number; adjustment_reason: string }) =>
    api<TaskWeight>(`/projects/${projectId}/tasks/${taskId}/weight`, json('PUT', data)),
}
