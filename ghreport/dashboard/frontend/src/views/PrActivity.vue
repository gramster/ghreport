<template>
  <div>
    <h2>{{ owner }}/{{ repo }} — PR Activity</h2>
    <div class="tabs">
      <router-link :to="{ name: 'repo-detail', params: { owner, repo } }">Overview</router-link>
      <router-link :to="{ name: 'issue-revisits', params: { owner, repo } }">Revisits</router-link>
      <router-link :to="{ name: 'pr-activity', params: { owner, repo } }">PR Activity</router-link>
      <router-link :to="{ name: 'closed-issues', params: { owner, repo } }">Closed Issues</router-link>
    </div>

    <div class="filters" style="margin-bottom: 1rem;">
      <label>Window (days):
        <input v-model.number="days" type="number" min="1" style="width: 60px; margin-left: 0.25rem;" />
      </label>
      <label>Since: <input type="date" v-model="since" /></label>
      <label>Until: <input type="date" v-model="until" /></label>
    </div>

    <div v-if="loading" class="loading">Loading...</div>
    <template v-else-if="data">
      <div v-for="(section, label) in sections" :key="label">
        <h3>{{ label }} ({{ section.length }})</h3>
        <table v-if="section.length">
          <thead><tr><th>#</th><th>Title</th><th>By</th><th>Created</th><th>Days</th><th>Lines</th></tr></thead>
          <tbody>
            <tr v-for="pr in section" :key="pr.number">
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
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import axios from 'axios'

interface PrItem {
  number: number; title: string; created_by: string; created_at: string
  days_open: number; lines_changed: number
}

interface PrActivityData {
  newly_opened: PrItem[]; newly_merged: PrItem[]
  newly_closed: PrItem[]; stale_open: PrItem[]
}

const props = defineProps<{ owner: string; repo: string }>()
const data = ref<PrActivityData | null>(null)
const loading = ref(true)
const days = ref(7)
const since = ref('')
const until = ref('')

const sections = computed<Record<string, PrItem[]>>(() => {
  if (!data.value) return {} as Record<string, PrItem[]>
  return {
    'Newly Opened': data.value.newly_opened || [],
    'Newly Merged': data.value.newly_merged || [],
    'Newly Closed (not merged)': data.value.newly_closed || [],
    'Stale Open': data.value.stale_open || [],
  }
})

async function load() {
  loading.value = true
  try {
    const params: Record<string, string | number | boolean> = { days: days.value, show_all: true }
    if (since.value) params.since = since.value
    if (until.value) params.until = until.value
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
watch([days, since, until], load)
</script>

<style scoped>
.filters {
  display: flex;
  gap: 1rem;
  align-items: center;
  flex-wrap: wrap;
}
.filters label {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}
.filters input {
  padding: 0.35rem;
  border: 1px solid #e1e4e8;
  border-radius: 4px;
}
</style>
