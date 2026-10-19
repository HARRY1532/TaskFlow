import { api } from './client'
import type { ProjectAnalytics } from '../types'

export const analyticsApi = {
  get: (projectId: number) => api<ProjectAnalytics>(`/projects/${projectId}/analytics`),
}
