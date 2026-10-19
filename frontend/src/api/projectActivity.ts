import { api } from './client'
import type { ProjectActivity } from '../types'

export const projectActivityApi = {
  list: () => api<ProjectActivity[]>('/admin/project-activities'),
  byUser: (userId: number) => api<ProjectActivity[]>(`/admin/users/${userId}/project-activities`),
  unreadCount: () => api<{ count: number }>('/admin/project-activities/unread-count'),
  markRead: (id: number) => api<ProjectActivity>(`/admin/project-activities/${id}/read`, { method: 'POST' }),
}
