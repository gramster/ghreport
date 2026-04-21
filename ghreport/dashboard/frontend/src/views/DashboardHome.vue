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
import ChartCard from '@/components/ChartCard.vue'

const dateRangeStore = useDateRangeStore()

interface AggSummary {
  total_open_issues: number; total_closed_issues: number
  total_open_prs: number; total_merged_prs: number; total_closed_prs: number
  repos: { owner: string; name: string }[]
}

const summary = ref<AggSummary | null>(null)
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    const { data } = await axios.get<AggSummary>('/api/aggregate/summary', {
      params: dateRangeStore.params,
    })
    summary.value = data
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => [dateRangeStore.since, dateRangeStore.until, dateRangeStore.coverageVersion], load)
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
</style>
