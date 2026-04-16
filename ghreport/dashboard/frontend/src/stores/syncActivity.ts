import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export interface SyncError {
  repo: string
  error: string
  when: string
}

export const useSyncActivityStore = defineStore('syncActivity', () => {
  const syncing = ref<string[]>([])
  const errors = ref<SyncError[]>([])
  let pollTimer: ReturnType<typeof setInterval> | null = null

  async function poll() {
    try {
      const { data } = await axios.get('/api/sync/activity')
      syncing.value = data.syncing || []
      errors.value = data.errors || []
    } catch {
      // Silently ignore polling failures
    }
  }

  function startPolling(intervalMs = 5000) {
    poll() // immediate first check
    if (pollTimer) clearInterval(pollTimer)
    pollTimer = setInterval(poll, intervalMs)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function dismissErrors() {
    try {
      await axios.delete('/api/sync/errors')
      errors.value = []
    } catch {
      // ignore
    }
  }

  return { syncing, errors, poll, startPolling, stopPolling, dismissErrors }
})
