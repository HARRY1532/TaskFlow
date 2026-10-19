import { api, json } from './client'
import type { AssignmentDecision, AssignmentDraft } from '../types'

const path = (projectId: number) => `/projects/${projectId}/assignments`
export const assignmentApi = {
  drafts: (projectId: number) => api<AssignmentDraft[]>(`${path(projectId)}/drafts`),
  suggest: (projectId: number) => api<AssignmentDraft>(`${path(projectId)}/suggest`, { method: 'POST' }),
  confirm: (projectId: number, draftId: number, assignments: AssignmentDecision[]) =>
    api<number[]>(`${path(projectId)}/drafts/${draftId}/confirm`, json('POST', { assignments })),
}
