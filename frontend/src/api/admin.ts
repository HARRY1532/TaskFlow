import { api, json } from './client'
import type { AdminUser, User } from '../types'

export const adminApi = {
  users: () => api<AdminUser[]>('/admin/users'),
  user: (id: number) => api<AdminUser>(`/admin/users/${id}`),
  create: (data: { email: string; name: string; password: string; is_admin: boolean }) =>
    api<User>('/admin/users', json('POST', data)),
  deactivate: (id: number, successorId: number | null) =>
    api<User>(`/admin/users/${id}${successorId ? `?successor_user_id=${successorId}` : ''}`, { method: 'DELETE' }),
  restore: (id: number) => api<User>(`/admin/users/${id}/restore`, { method: 'POST' }),
}
