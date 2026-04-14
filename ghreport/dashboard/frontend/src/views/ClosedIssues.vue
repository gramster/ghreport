<template>
  <div>
    <h2>{{ owner }}/{{ repo }} — Recently Closed Issues</h2>
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
      <p>{{ data.issues?.length || 0 }} issues closed in the last {{ days }} day(s)</p>
      <table v-if="data.issues?.length">
        <thead><tr><th>#</th><th>Title</th><th>By</th><th>Closed</th><th>Closed By</th><th>Days Open</th></tr></thead>
        <tbody>
          <tr v-for="issue in data.issues" :key="issue.number">
            <td>{{ issue.number }}</td>
            <td>{{ issue.title }}</td>
            <td>{{ issue.created_by }}</td>
            <td>{{ issue.closed_at }}</td>
            <td>{{ issue.closed_by }}</td>
            <td>{{ issue.days_open }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import axios from 'axios'

interface ClosedIssue {
  number: number; title: string; created_by: string
  closed_at: string | null; closed_by: string | null; days_open: number
}

interface ClosedIssuesData {
  issues: ClosedIssue[]
}

const props = defineProps<{ owner: string; repo: string }>()
const data = ref<ClosedIssuesData | null>(null)
const loading = ref(true)
const days = ref(7)

async function load() {
  loading.value = true
  try {
    const { data: d } = await axios.get(
      `/api/repos/${props.owner}/${props.repo}/reports/closed-issues`,
      { params: { days: days.value } },
    )
    data.value = d
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => [props.owner, props.repo], load)
</script>
