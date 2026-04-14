<template>
  <div>
    <h2>{{ owner }}/{{ repo }} — PR Activity</h2>
    <div class="tabs">
      <router-link :to="{ name: 'repo-detail', params: { owner, repo } }">Overview</router-link>
      <router-link :to="{ name: 'issue-revisits', params: { owner, repo } }">Revisits</router-link>
      <router-link :to="{ name: 'pr-activity', params: { owner, repo } }">PR Activity</router-link>
      <router-link :to="{ name: 'closed-issues', params: { owner, repo } }">Closed Issues</router-link>
    </div>

    <div style="margin-bottom: 1rem;">
      <label>Window (days):
        <input v-model.number="days" type="number" min="1" style="width: 60px; margin-left: 0.25rem;" />
      </label>
      <button @click="load" style="margin-left: 0.5rem;">Refresh</button>
    </div>

    <div v-if="loading" class="loading">Loading...</div>
    <template v-else-if="data">
      <div v-for="(section, label) in sections" :key="label">
        <h3>{{ label }} ({{ section.length }})</h3>
        <table v-if="section.length">
          <thead><tr><th>#</th><th>Title</th><th>By</th><th>Created</th><th>Days</th><th>Lines</th></tr></thead>
          <tbody>
            <tr v-for="pr in section" :key="pr.number">
              <td>{{ pr.number }}</td>
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

const props = defineProps<{ owner: string; repo: string }>()
const data = ref<Record<string, unknown[]> | null>(null)
const loading = ref(true)
const days = ref(7)

const sections = computed(() => {
  if (!data.value) return {}
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
    const { data: d } = await axios.get(
      `/api/repos/${props.owner}/${props.repo}/reports/pr-activity`,
      { params: { days: days.value, show_all: true } },
    )
    data.value = d
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => [props.owner, props.repo], load)
</script>
