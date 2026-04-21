<template>
  <div>
    <h2>{{ owner }}/{{ repo }} — PR Activity</h2>
    <div class="tabs">
      <router-link :to="{ name: 'repo-detail', params: { owner, repo } }">Overview</router-link>
      <router-link :to="{ name: 'issue-revisits', params: { owner, repo } }">Revisits</router-link>
      <router-link :to="{ name: 'pr-activity', params: { owner, repo } }">PR Activity</router-link>
      <router-link :to="{ name: 'closed-issues', params: { owner, repo } }">Closed Issues</router-link>
      <router-link :to="{ name: 'insights', params: { owner, repo } }">Insights</router-link>
    </div>

    <div v-if="loading" class="loading">Loading...</div>
    <template v-else-if="data">
      <div class="filter-row" style="margin-bottom: 0.75rem;">
        <span class="filter-label">Status:</span>
        <button :class="{ active: activeCat === 'newly_opened' }" @click="activeCat = 'newly_opened'">Newly Opened</button>
        <button :class="{ active: activeCat === 'newly_merged' }" @click="activeCat = 'newly_merged'">Newly Merged</button>
        <button :class="{ active: activeCat === 'newly_closed' }" @click="activeCat = 'newly_closed'">Newly Abandoned</button>
        <span style="margin-left: 1rem;"></span>
        <button :class="{ active: activeCat === 'stale_open' }" @click="activeCat = 'stale_open'">Stale Open</button>
      </div>

      <h3>{{ catLabels[activeCat] }} ({{ activeItems.length }})</h3>
      <table v-if="activeItems.length">
        <thead><tr>
          <th class="sortable" @click="toggleSort('number')">#{{ indicator('number') }}</th>
          <th class="sortable" @click="toggleSort('title')">Title{{ indicator('title') }}</th>
          <th class="sortable" @click="toggleSort('created_by')">By{{ indicator('created_by') }}</th>
          <th class="sortable" @click="toggleSort('created_at')">Created{{ indicator('created_at') }}</th>
          <th class="sortable" @click="toggleSort('days_open')">Days{{ indicator('days_open') }}</th>
          <th class="sortable" @click="toggleSort('lines_changed')">Lines{{ indicator('lines_changed') }}</th>
        </tr></thead>
        <tbody>
          <tr v-for="pr in sortedItems" :key="pr.number">
            <td><a :href="`https://github.com/${owner}/${repo}/pull/${pr.number}`" target="_blank">{{ pr.number }}</a></td>
            <td>{{ pr.title }}</td>
            <td>{{ pr.created_by }}</td>
            <td>{{ pr.created_at }}</td>
            <td>{{ pr.days_open }}</td>
            <td>{{ pr.lines_changed }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else style="color: #586069; margin-left: 1rem;">None</p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import axios from 'axios'
import { useDateRangeStore } from '@/stores/dateRange'

interface PrItem {
  number: number; title: string; created_by: string; created_at: string
  days_open: number; lines_changed: number
}

interface PrActivityData {
  newly_opened: PrItem[]; newly_merged: PrItem[]
  newly_closed: PrItem[]; stale_open: PrItem[]
}

const props = defineProps<{ owner: string; repo: string }>()
const dateRange = useDateRangeStore()
const data = ref<PrActivityData | null>(null)
const loading = ref(true)
const activeCat = ref<string>('newly_opened')

const catLabels: Record<string, string> = {
  newly_opened: 'Newly Opened',
  newly_merged: 'Newly Merged',
  newly_closed: 'Newly Abandoned',
  stale_open: 'Stale Open',
}

const activeItems = computed<PrItem[]>(() => {
  if (!data.value) return []
  return (data.value as any)[activeCat.value] || []
})

const sortState = reactive<{ key: string; dir: 'asc' | 'desc' }>({ key: '', dir: 'asc' })

function toggleSort(key: string) {
  if (sortState.key === key) {
    sortState.dir = sortState.dir === 'asc' ? 'desc' : 'asc'
  } else {
    sortState.key = key
    sortState.dir = 'asc'
  }
}

function indicator(key: string): string {
  if (sortState.key !== key) return ''
  return sortState.dir === 'asc' ? ' ▲' : ' ▼'
}

const sortedItems = computed<PrItem[]>(() => {
  if (!sortState.key) return activeItems.value
  const dir = sortState.dir === 'asc' ? 1 : -1
  const k = sortState.key as keyof PrItem
  return [...activeItems.value].sort((a, b) => {
    const av = a[k], bv = b[k]
    if (av == null && bv == null) return 0
    if (av == null) return dir
    if (bv == null) return -dir
    if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir
    return String(av).localeCompare(String(bv)) * dir
  })
})

async function load() {
  loading.value = true
  try {
    const params: Record<string, string | number | boolean> = {
      days: dateRange.effectiveDays, show_all: true, ...dateRange.params,
    }
    const { data: d } = await axios.get(
      `/api/repos/${props.owner}/${props.repo}/reports/pr-activity`,
      { params },
    )
    data.value = d
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => [props.owner, props.repo], load)
watch(() => [dateRange.since, dateRange.until, dateRange.coverageVersion], load)
</script>

<style scoped>
.filter-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.filter-label {
  font-weight: 600;
  font-size: 0.9rem;
  margin-right: 0.25rem;
}
.filter-row button {
  padding: 0.4rem 1rem;
  border: 1px solid #e1e4e8;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
}
.filter-row button.active {
  background: #0366d6;
  color: #fff;
  border-color: #0366d6;
}
</style>
