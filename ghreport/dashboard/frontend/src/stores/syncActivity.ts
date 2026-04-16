import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

export interface SyncError {
  repo: string
  error: string
  when: string
}

export interface RetryInfo {
  attempt: number
  max_attempts: number
  delay: number
  error: string
}

export const useSyncActivityStore = defineStore('syncActivity', () => {
  const syncing = ref<string[]>([])
  const retries = ref<Record<string, RetryInfo>>({})
  const errors = ref<SyncError[]>([])
  let pollTimer: ReturnType<typeof setInterval> | null = null

  const hasRetries = computed(() => Object.keys(retries.value).length > 0)

  const syncTooltip = computed(() => {
    const parts: string[] = []
    for (const repo of syncing.value) {
      const r = retries.value[repo]
      if (r) {
        parts.push(`${repo}: retrying ${r.attempt}/${r.max_attempts} (next in ${r.delay}s)`)
      } else {
        parts.push(repo)
      }
    }
    return parts.length ? 'Syncing: ' + parts.join(', ') : ''
  })

  async function poll() {
    try {
      const { data } = await axios.get('/api/sync/activity')
      syncing.value = data.syncing || []
      retries.value = data.retries || {}
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

  return { syncing, retries, errors, hasRetries, syncTooltip, poll, startPolling, stopPolling, dismissErrors }
})
