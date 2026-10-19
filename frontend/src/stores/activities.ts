import { defineStore } from 'pinia'
import { ref } from 'vue'
import { projectActivityApi } from '../api/projectActivity'

export const useActivitiesStore = defineStore('activities', () => {
  const unreadCount = ref(0)
  async function refresh() {
    const result = await projectActivityApi.unreadCount()
    unreadCount.value = result.count
  }
  function clear() { unreadCount.value = 0 }
  return { unreadCount, refresh, clear }
})
