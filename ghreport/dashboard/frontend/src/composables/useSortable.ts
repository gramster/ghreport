import { ref, computed, type Ref } from 'vue'

type SortDir = 'asc' | 'desc'

export function useSortable<T>(items: Ref<T[]>, defaultKey?: string, defaultDir: SortDir = 'asc') {
  const sortKey = ref<string>(defaultKey ?? '')
  const sortDir = ref<SortDir>(defaultDir)

  function toggleSort(key: string) {
    if (sortKey.value === key) {
      sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
    } else {
      sortKey.value = key
      sortDir.value = 'asc'
    }
  }

  function sortIndicator(key: string): string {
    if (sortKey.value !== key) return ''
    return sortDir.value === 'asc' ? ' ▲' : ' ▼'
  }

  const sorted = computed(() => {
    if (!sortKey.value) return items.value
    const k = sortKey.value
    const dir = sortDir.value === 'asc' ? 1 : -1
    return [...items.value].sort((a, b) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const av = (a as any)[k]
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const bv = (b as any)[k]
      if (av == null && bv == null) return 0
      if (av == null) return dir
      if (bv == null) return -dir
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir
      return String(av).localeCompare(String(bv)) * dir
    })
  })

  return { sortKey, sortDir, toggleSort, sortIndicator, sorted }
}
