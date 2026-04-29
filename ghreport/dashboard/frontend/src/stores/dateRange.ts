import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import axios from 'axios'

function fmt(d: Date): string {
  return d.toISOString().slice(0, 10)
}

function loadSaved(key: string, fallback: string): string {
  try {
    const v = localStorage.getItem(key)
    if (v && /^\d{4}-\d{2}-\d{2}$/.test(v)) return v
  } catch { /* ignore */ }
  return fallback
}

export const useDateRangeStore = defineStore('dateRange', () => {
  const now = new Date()
  const weekAgo = new Date(now.getTime() - 7 * 86400000)
  const since = ref(loadSaved('ghreport_since', fmt(weekAgo)))
  const until = ref(loadSaved('ghreport_until', fmt(now)))
  const backfilling = ref(false)

  // Persist to localStorage on change
  watch(since, (v) => { try { localStorage.setItem('ghreport_since', v) } catch { /* */ } })
  watch(until, (v) => { try { localStorage.setItem('ghreport_until', v) } catch { /* */ } })

  const params = computed(() => {
    const p: Record<string, string> = {}
    if (since.value) p.since = since.value
    if (until.value) p.until = until.value
    return p
  })

  const effectiveDays = computed(() => {
    if (!since.value) return 7
    const s = new Date(since.value)
    const u = until.value ? new Date(until.value) : new Date()
    return Math.max(1, Math.round((u.getTime() - s.getTime()) / 86400000))
  })

  // When 'since' changes, check if we need to backfill older data
  let checkTimer: ReturnType<typeof setTimeout> | null = null
  // Track the last since value we confirmed coverage for, to skip redundant checks
  let lastCoveredSince: string | null = null
  watch(since, (val) => {
    if (val === lastCoveredSince) return
    if (checkTimer) clearTimeout(checkTimer)
    // Debounce to avoid rapid-fire calls while typing
    checkTimer = setTimeout(() => checkCoverage(val), 500)
  })

  async function checkCoverage(sinceVal: string) {
    if (!sinceVal) return
    try {
      const { data } = await axios.post('/api/coverage/check', null, {
        params: { since: sinceVal },
      })
      if (data.backfilling) {
        backfilling.value = true
        // Poll until backfill completes, then clear flag to trigger re-render
        pollUntilCovered(sinceVal)
      } else {
        // Data is already covered — remember so we don't re-check
        lastCoveredSince = sinceVal
      }
    } catch {
      // Silently ignore — data will still show whatever is cached
    }
  }

  async function pollUntilCovered(sinceVal: string) {
    // Check every 5 seconds, up to 2 minutes
    for (let i = 0; i < 24; i++) {
      await new Promise(r => setTimeout(r, 5000))
      try {
        const { data } = await axios.post('/api/coverage/check', null, {
          params: { since: sinceVal },
        })
        if (!data.backfilling) {
          backfilling.value = false
          // Bump a version counter to trigger watchers
          coverageVersion.value++
          return
        }
      } catch {
        // continue polling
      }
    }
    // 2-minute window expired without success (e.g. rate-limited).
    // Schedule a retry so the backfill eventually runs once the rate
    // limit clears, without requiring the user to change the date.
    backfilling.value = false
    setTimeout(() => {
      if (since.value === sinceVal && lastCoveredSince !== sinceVal) {
        checkCoverage(sinceVal)
      }
    }, 5 * 60 * 1000)
  }

  // Incremented when a backfill completes, so views can refetch
  const coverageVersion = ref(0)

  // Check coverage immediately on store init (catches cases where the
  // app reloads after a previous poll timed out or a rate limit)
  checkCoverage(since.value)

  return { since, until, params, effectiveDays, backfilling, coverageVersion }
})
