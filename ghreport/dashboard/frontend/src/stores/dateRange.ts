import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

function fmt(d: Date): string {
  return d.toISOString().slice(0, 10)
}

export const useDateRangeStore = defineStore('dateRange', () => {
  const now = new Date()
  const weekAgo = new Date(now.getTime() - 7 * 86400000)
  const since = ref(fmt(weekAgo))
  const until = ref(fmt(now))

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

  return { since, until, params, effectiveDays }
})
