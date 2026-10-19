import { api, baseUrl, json, ApiError } from './client'
import type { User } from '../types'

export const profileApi = {
  update: (name: string) => api<User>('/profile', json('PATCH', { name })),
  changePassword: (current_password: string, new_password: string) =>
    api<{ message: string }>('/profile/password', json('POST', { current_password, new_password })),
  async uploadAvatar(file: File): Promise<User> {
    const body = new FormData()
    body.append('file', file)
    const token = localStorage.getItem('taskflow_token')
    const response = await fetch(`${baseUrl}/profile/avatar`, {
      method: 'POST', body,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new ApiError(response.status, typeof data.detail === 'string' ? data.detail : '上传失败')
    return data as User
  },
}
