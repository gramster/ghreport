import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import axios from 'axios'

function fmt(d: Date): string {
  return d.toISOString().slice(0, 10)
}

export const useDateRangeStore = defineStore('dateRange', () => {
  const now = new Date()
  const weekAgo = new Date(now.getTime() - 7 * 86400000)
  const since = ref(fmt(weekAgo))
  const until = ref(fmt(now))
  const backfilling = ref(false)

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
  watch(since, (val) => {
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
    backfilling.value = false
  }

  // Incremented when a backfill completes, so views can refetch
  const coverageVersion = ref(0)

  return { since, until, params, effectiveDays, backfilling, coverageVersion }
})
