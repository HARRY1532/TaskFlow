import { api, json } from './client'
import type { User } from '../types'

export const authApi = {
  register: (data: { email: string; name: string; password: string }) =>
    api<User>('/auth/register', json('POST', data)),
  login: (data: { email: string; password: string }) =>
    api<{ access_token: string }>('/auth/login', json('POST', data)),
  me: () => api<User>('/auth/me'),
}
