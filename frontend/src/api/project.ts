import { api, json } from './client'
import type { Invitation, Member, Project } from '../types'

export const projectApi = {
  list: () => api<Project[]>('/projects'),
  get: (id: number) => api<Project>(`/projects/${id}`),
  create: (data: { name: string; goal: string; requirements: string; tech_stack: string }) =>
    api<Project>('/projects', json('POST', data)),
  update: (id: number, data: { name: string; goal: string; requirements: string; tech_stack: string; start_date: string | null; end_date: string | null }) =>
    api<Project>(`/projects/${id}`, json('PUT', data)),
  setRepository: (id: number, url: string | null) =>
    api<Project>(`/projects/${id}/repository`, json('PUT', { url })),
  remove: (id: number, confirmation: string) =>
    api<void>(`/projects/${id}?confirmation=${encodeURIComponent(confirmation)}`, { method: 'DELETE' }),
  leave: (id: number, confirmation: string) =>
    api<void>(`/projects/${id}/members/me?confirmation=${encodeURIComponent(confirmation)}`, { method: 'DELETE' }),
  transferOwner: (id: number, newOwnerId: number) =>
    api<Project>(`/projects/${id}/owner`, json('PUT', { new_owner_id: newOwnerId })),
  members: (id: number) => api<Member[]>(`/projects/${id}/members`),
  invite: (id: number, email: string) =>
    api<Invitation>(`/projects/${id}/invitations`, json('POST', { email })),
  invitations: (id: number) => api<Invitation[]>(`/projects/${id}/invitations`),
  cancelInvitation: (id: number, invitationId: number) =>
    api<Invitation>(`/projects/${id}/invitations/${invitationId}/cancel`, { method: 'POST' }),
}
