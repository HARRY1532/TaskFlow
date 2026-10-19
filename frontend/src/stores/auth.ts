import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authApi } from '../api/auth'
import type { User } from '../types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const token = ref(localStorage.getItem('taskflow_token'))
  async function load() {
    if (!token.value) return
    try { user.value = await authApi.me() }
    catch { logout() }
  }
  async function login(email: string, password: string) {
    const result = await authApi.login({ email, password })
    token.value = result.access_token
    localStorage.setItem('taskflow_token', token.value)
    await load()
  }
  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('taskflow_token')
  }
  function setUser(value: User) { user.value = value }
  return { user, token, load, login, logout, setUser }
})
