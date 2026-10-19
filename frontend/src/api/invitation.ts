import { api } from './client'
import type { Invitation } from '../types'

export const invitationApi = {
  list: () => api<Invitation[]>('/invitations'),
  accept: (id: number) => api<Invitation>(`/invitations/${id}/accept`, { method: 'POST' }),
  decline: (id: number) => api<Invitation>(`/invitations/${id}/decline`, { method: 'POST' }),
}
