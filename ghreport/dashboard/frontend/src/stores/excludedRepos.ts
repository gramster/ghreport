import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const STORAGE_KEY = 'ghreport_excluded_repos'

function loadExcluded(): Set<string> {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v) return new Set(JSON.parse(v))
  } catch { /* ignore */ }
  return new Set()
}

export const useExcludedReposStore = defineStore('excludedRepos', () => {
  const excluded = ref<Set<string>>(loadExcluded())

  function save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify([...excluded.value]))
    } catch { /* ignore */ }
  }

  function toggle(owner: string, name: string) {
    const key = `${owner}/${name}`
    if (excluded.value.has(key)) {
      excluded.value.delete(key)
    } else {
      excluded.value.add(key)
    }
    // Trigger reactivity by replacing the Set reference
    excluded.value = new Set(excluded.value)
    save()
  }

  function isExcluded(owner: string, name: string) {
    return excluded.value.has(`${owner}/${name}`)
  }

  // Array of "owner/name" strings for use as query params
  const excludeParams = computed(() => [...excluded.value])

  return { excluded, excludeParams, toggle, isExcluded }
})
