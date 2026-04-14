<template>
  <div>
    <h2>Dashboard</h2>
    <div v-if="loading" class="loading">Loading...</div>
    <template v-else>
      <div v-if="summary" class="grid" style="margin-bottom: 1.5rem;">
        <div class="card">
          <div class="stat">{{ summary.total_open_issues }}</div>
          <div class="stat-label">Open Issues</div>
        </div>
        <div class="card">
          <div class="stat">{{ summary.total_closed_issues }}</div>
          <div class="stat-label">Closed Issues</div>
        </div>
        <div class="card">
          <div class="stat">{{ summary.total_open_prs }}</div>
          <div class="stat-label">Open PRs</div>
        </div>
        <div class="card">
          <div class="stat">{{ summary.total_merged_prs }}</div>
          <div class="stat-label">Merged PRs</div>
        </div>
      </div>

      <h3>Repositories</h3>
      <div class="grid">
        <div v-for="r in summary?.repos" :key="`${r.owner}/${r.name}`" class="card">
          <h3>
            <router-link :to="{ name: 'repo-detail', params: { owner: r.owner, repo: r.name } }">
              {{ r.owner }}/{{ r.name }}
            </router-link>
          </h3>
          <p>
            <span class="badge open">{{ r.open_issues }} open issues</span>
            <span class="badge merged" style="margin-left: 0.5rem;">{{ r.merged_prs }} merged PRs</span>
          </p>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'

interface RepoSummaryItem {
  owner: string; name: string
  open_issues: number; closed_issues: number
  open_prs: number; merged_prs: number; closed_prs: number
}

interface AggSummary {
  total_open_issues: number; total_closed_issues: number
  total_open_prs: number; total_merged_prs: number; total_closed_prs: number
  repos: RepoSummaryItem[]
}

const summary = ref<AggSummary | null>(null)
const loading = ref(true)

onMounted(async () => {
  try {
    const { data } = await axios.get<AggSummary>('/api/aggregate/summary')
    summary.value = data
  } finally {
    loading.value = false
  }
})
</script>
