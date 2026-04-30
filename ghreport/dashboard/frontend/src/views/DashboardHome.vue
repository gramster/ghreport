<template>
  <div>
    <div class="title-bar">
      <h2>Dashboard</h2>
    </div>
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

      <!-- Repo filter -->
      <div v-if="summary && summary.repos.length > 1" class="repo-filter card">
        <span class="filter-label">Repos in aggregate:</span>
        <label v-for="r in summary.repos" :key="`${r.owner}/${r.name}`" class="repo-toggle">
          <input
            type="checkbox"
            :checked="!excludedRepos.isExcluded(r.owner, r.name)"
            @change="excludedRepos.toggle(r.owner, r.name)"
          />
          {{ r.name }}
        </label>
      </div>

      <template v-if="summary && summary.repos.length >= 1">
        <h3 style="margin-top: 1.5rem;">Aggregate Charts</h3>
        <div class="chart-grid-wide">
          <ChartCard title="Response Times (median days/week)" :aggregate="true" chart-type="time-to-combined" y-label="Days" />
          <ChartCard title="Weekly Activity Counts" :aggregate="true" chart-type="activity-counts" y-label="Count" />
        </div>
        <div class="chart-grid-narrow">
          <ChartCard title="Open Issues" :aggregate="true" chart-type="open-issues" />
          <ChartCard title="Label Frequency" :aggregate="true" chart-type="label-frequency" />
          <ChartCard title="Top Terms" :aggregate="true" chart-type="top-terms" />
        </div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import axios from 'axios'
import { useDateRangeStore } from '@/stores/dateRange'
import { useExcludedReposStore } from '@/stores/excludedRepos'
import ChartCard from '@/components/ChartCard.vue'

const dateRangeStore = useDateRangeStore()
const excludedRepos = useExcludedReposStore()

interface RepoSummary {
  owner: string; name: string
  open_issues: number; closed_issues: number
  open_prs: number; merged_prs: number; closed_prs: number
}

interface AggSummary {
  total_open_issues: number; total_closed_issues: number
  total_open_prs: number; total_merged_prs: number; total_closed_prs: number
  repos: RepoSummary[]
}

const summary = ref<AggSummary | null>(null)
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    const params: Record<string, unknown> = { ...dateRangeStore.params }
    if (excludedRepos.excludeParams.length) params.exclude = excludedRepos.excludeParams
    const { data } = await axios.get<AggSummary>('/api/aggregate/summary', { params })
    summary.value = data
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => [dateRangeStore.since, dateRangeStore.until, dateRangeStore.coverageVersion, excludedRepos.excludeParams], load)
</script>

<style scoped>
.title-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.5rem;
}
.title-bar h2 { margin: 0; }
.repo-filter {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
  padding: 0.6rem 1rem;
  margin-bottom: 1rem;
}
.filter-label {
  font-size: 0.85rem;
  color: #666;
  white-space: nowrap;
}
.repo-toggle {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.85rem;
  cursor: pointer;
  user-select: none;
}
.repo-toggle input { cursor: pointer; }
</style>
