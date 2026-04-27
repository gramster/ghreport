<template>
  <div>
    <h2>{{ owner }}/{{ repo }} — Issue Revisits</h2>
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
        <span class="filter-label">Type:</span>
        <button :class="{ active: activeTab === 'bugs' }" @click="activeTab = 'bugs'">Bugs</button>
        <button :class="{ active: activeTab === 'non_bugs' }" @click="activeTab = 'non_bugs'">Non-Bugs</button>
      </div>
      <div class="filter-row" style="margin-bottom: 0.75rem;">
        <span class="filter-label">Last Response By:</span>
        <button :class="{ active: activeCat === 'needs_response' }" @click="activeCat = 'needs_response'">None</button>
        <button :class="{ active: activeCat === 'op_responded' }" @click="activeCat = 'op_responded'">Creator</button>
        <button :class="{ active: activeCat === 'third_party_responded' }" @click="activeCat = 'third_party_responded'">3rd Party</button>
        <span style="margin-left: 1rem;"></span>
        <button :class="{ active: activeCat === 'stale' }" @click="activeCat = 'stale'">Stale</button>
      </div>
      <div class="filter-row" style="margin-bottom: 0.75rem;">
        <span class="filter-label">Min reactions:</span>
        <input type="number" v-model.number="minReactions" min="0" style="width: 4rem; padding: 0.3rem; border: 1px solid #e1e4e8; border-radius: 4px;" />
      </div>

      <h3>{{ activeTab === 'bugs' ? 'Bug Issues' : 'Non-Bug Issues' }} — {{ formatCat(activeCat) }} ({{ filteredItems.length }})</h3>
      <table v-if="filteredItems.length">
        <thead><tr>
          <th class="sortable" @click="toggleSort('number')">#{{ indicator('number') }}</th>
          <th class="sortable" @click="toggleSort('title')">Title{{ indicator('title') }}</th>
          <th class="sortable" @click="toggleSort('created_by')">Created By{{ indicator('created_by') }}</th>
          <th class="sortable" @click="toggleSort('created_at')">Created{{ indicator('created_at') }}</th>
          <th class="sortable" @click="toggleSort('reactions')">Reactions{{ indicator('reactions') }}</th>
          <th></th>
        </tr></thead>
        <tbody>
          <tr v-for="issue in sortedItems" :key="issue.number">
            <td><a :href="`https://github.com/${owner}/${repo}/issues/${issue.number}`" target="_blank">{{ issue.number }}</a></td>
            <td>{{ issue.title }}</td>
            <td>{{ issue.created_by }}</td>
            <td>{{ issue.created_at }}</td>
            <td>{{ issue.reactions ?? 0 }}</td>
            <td><span v-if="issue.star" class="star">★</span></td>
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

interface RevisitIssue {
  number: number; title: string; created_by: string; created_at: string; star: boolean
  days_op?: number; days_team?: number; days_third_party?: number; reactions?: number
}

interface RevisitsData {
  sections: Record<string, Record<string, RevisitIssue[]>>
}

const props = defineProps<{ owner: string; repo: string }>()
const dateRange = useDateRangeStore()
const data = ref<RevisitsData | null>(null)
const loading = ref(true)
const activeTab = ref<'bugs' | 'non_bugs'>('bugs')
const activeCat = ref<string>('needs_response')

const catLabels: Record<string, string> = {
  needs_response: 'Needs Response',
  op_responded: 'Creator Responded',
  third_party_responded: '3rd Party Responded',
  stale: 'Stale',
}

function formatCat(key: string): string {
  return catLabels[key] || key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

const activeItems = computed<RevisitIssue[]>(() => {
  return data.value?.sections[activeTab.value]?.[activeCat.value] || []
})

const minReactions = ref(0)

const filteredItems = computed<RevisitIssue[]>(() => {
  if (minReactions.value <= 0) return activeItems.value
  return activeItems.value.filter(i => (i.reactions ?? 0) >= minReactions.value)
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

const sortedItems = computed<RevisitIssue[]>(() => {
  if (!sortState.key) return filteredItems.value
  const dir = sortState.dir === 'asc' ? 1 : -1
  const k = sortState.key as keyof RevisitIssue
  return [...filteredItems.value].sort((a, b) => {
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
    const { data: d } = await axios.get(`/api/repos/${props.owner}/${props.repo}/reports/revisits`, {
      params: { show_all: true, ...dateRange.params },
    })
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
