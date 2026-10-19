import { api } from './client'
import type { ProgressReport, ProgressSnapshot } from '../types'

const path = (projectId: number) => `/projects/${projectId}/progress`
export const progressApi = {
  snapshot: (projectId: number) => api<ProgressSnapshot>(`${path(projectId)}/snapshot`),
  reports: (projectId: number) => api<ProgressReport[]>(`${path(projectId)}/reports`),
  generate: (projectId: number) => api<ProgressReport>(`${path(projectId)}/reports`, { method: 'POST' }),
}
