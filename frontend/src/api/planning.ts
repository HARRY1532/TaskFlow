import { api, json } from './client'
import type { PlanningConfirmTask, PlanningDraft } from '../types'

export const planningApi = {
  drafts: (projectId: number) => api<PlanningDraft[]>(`/projects/${projectId}/planning/drafts`),
  suggest: (projectId: number) => api<PlanningDraft>(`/projects/${projectId}/planning/suggest`, { method: 'POST' }),
  confirm: (projectId: number, draftId: number, tasks: PlanningConfirmTask[]) =>
    api<number[]>(`/projects/${projectId}/planning/drafts/${draftId}/confirm`, json('POST', { tasks })),
}
