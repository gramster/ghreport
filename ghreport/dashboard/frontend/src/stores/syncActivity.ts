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
  const rateLimitedUntil = ref<string | null>(null)
  const errors = ref<SyncError[]>([])
  let pollTimer: ReturnType<typeof setInterval> | null = null

  const hasRetries = computed(() => Object.keys(retries.value).length > 0)

  const isRateLimited = computed(() => {
    if (!rateLimitedUntil.value) return false
    return new Date(rateLimitedUntil.value) > new Date()
  })

  const rateLimitRemaining = computed(() => {
    if (!rateLimitedUntil.value) return 0
    const diff = new Date(rateLimitedUntil.value).getTime() - Date.now()
    return Math.max(0, Math.ceil(diff / 1000))
  })

  const syncTooltip = computed(() => {
    if (isRateLimited.value) {
      const mins = Math.ceil(rateLimitRemaining.value / 60)
      return `Rate limited — cooldown ${mins}m remaining`
    }
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
      rateLimitedUntil.value = data.rate_limited_until || null
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

  return { syncing, retries, rateLimitedUntil, errors, hasRetries, isRateLimited, rateLimitRemaining, syncTooltip, poll, startPolling, stopPolling, dismissErrors }
})
