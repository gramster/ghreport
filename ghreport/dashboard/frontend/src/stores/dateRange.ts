import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useDateRangeStore = defineStore('dateRange', () => {
  const since = ref('')
  const until = ref('')

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
