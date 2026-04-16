<template>
  <div>
    <div class="title-bar">
      <h2>{{ owner }}/{{ repo }}</h2>
      <div class="title-actions">
        <span v-if="repoInfo?.last_synced_at" class="sync-time">{{ new Date(repoInfo.last_synced_at).toLocaleString() }}</span>
        <span v-if="syncError" class="sync-error" :title="syncError">⚠ Sync error</span>
        <button class="primary" @click="triggerSync" :disabled="syncing">
          {{ syncing ? 'Syncing...' : 'Sync Now' }}
        </button>
      </div>
    </div>
    <div class="tabs">
      <router-link :to="{ name: 'repo-detail', params: { owner, repo } }">Overview</router-link>
      <router-link :to="{ name: 'issue-revisits', params: { owner, repo } }">Revisits</router-link>
      <router-link :to="{ name: 'pr-activity', params: { owner, repo } }">PR Activity</router-link>
      <router-link :to="{ name: 'closed-issues', params: { owner, repo } }">Closed Issues</router-link>
    </div>

    <div v-if="loading" class="loading">Loading...</div>
    <template v-else-if="repoInfo">
      <div class="grid" style="margin-bottom: 1.5rem">
        <div class="card">
          <div class="stat">{{ repoInfo.issues?.open || 0 }}</div>
          <div class="stat-label">Open Issues</div>
          <div v-if="repoInfo.date_ranges?.issues_open" class="stat-range">{{ formatRange(repoInfo.date_ranges.issues_open) }}</div>
        </div>
        <div class="card">
          <div class="stat">{{ repoInfo.issues?.closed || 0 }}</div>
          <div class="stat-label">Closed Issues</div>
          <div v-if="repoInfo.date_ranges?.issues_closed" class="stat-range">{{ formatRange(repoInfo.date_ranges.issues_closed) }}</div>
        </div>
        <div class="card">
          <div class="stat">{{ repoInfo.pull_requests?.open || 0 }}</div>
          <div class="stat-label">Open PRs</div>
          <div v-if="repoInfo.date_ranges?.prs_open" class="stat-range">{{ formatRange(repoInfo.date_ranges.prs_open) }}</div>
        </div>
        <div class="card">
          <div class="stat">{{ repoInfo.pull_requests?.merged || 0 }}</div>
          <div class="stat-label">Merged PRs</div>
          <div v-if="repoInfo.date_ranges?.prs_merged" class="stat-range">{{ formatRange(repoInfo.date_ranges.prs_merged) }}</div>
        </div>
      </div>

      <h3 style="margin-top: 1rem;">Charts</h3>
      <div class="grid">
        <ChartCard :key="'open-issues-'+syncVersion" title="Open Issues" :owner="owner" :repo="repo" chart-type="open-issues" />
        <ChartCard :key="'time-to-merge-'+syncVersion" title="Time to Merge (days)" :owner="owner" :repo="repo" chart-type="time-to-merge" />
        <ChartCard :key="'time-to-close-'+syncVersion" title="Time to Close (days)" :owner="owner" :repo="repo" chart-type="time-to-close" />
        <ChartCard :key="'time-to-response-'+syncVersion" title="Time to Response (days)" :owner="owner" :repo="repo" chart-type="time-to-response" />
        <ChartCard :key="'label-frequency-'+syncVersion" title="Label Frequency" :owner="owner" :repo="repo" chart-type="label-frequency" />
        <ChartCard :key="'files-changed-'+syncVersion" title="Files Changed/PR" :owner="owner" :repo="repo" chart-type="files-changed" y-label="Files" />
        <ChartCard :key="'lines-changed-'+syncVersion" title="Lines Changed/PR" :owner="owner" :repo="repo" chart-type="lines-changed" y-label="Lines" />
        <ChartCard :key="'top-terms-'+syncVersion" title="Top Terms" :owner="owner" :repo="repo" chart-type="top-terms" />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import axios from 'axios'
import { useDateRangeStore } from '@/stores/dateRange'
import { useSyncActivityStore } from '@/stores/syncActivity'
import ChartCard from '@/components/ChartCard.vue'

interface DateRange {
  earliest: string
  latest: string
}

interface RepoInfo {
  issues: Record<string, number>
  pull_requests: Record<string, number>
  last_synced_at: string | null
  date_ranges?: Record<string, DateRange>
}

const props = defineProps<{ owner: string; repo: string }>()
const dateRange = useDateRangeStore()
const syncActivityStore = useSyncActivityStore()
const repoInfo = ref<RepoInfo | null>(null)
const loading = ref(true)
const syncing = ref(false)
const syncVersion = ref(0)

const syncError = computed(() => {
  const key = `${props.owner}/${props.repo}`
  const err = syncActivityStore.errors.find(e => e.repo === key)
  return err ? err.error : ''
})

function formatRange(range: DateRange): string {
  const fmt = (s: string) => s.slice(0, 10)
  return `${fmt(range.earliest)} — ${fmt(range.latest)}`
}

async function load() {
  loading.value = true
  try {
    const { data } = await axios.get(`/api/repos/${props.owner}/${props.repo}`, {
      params: dateRange.params,
    })
    repoInfo.value = data
  } finally {
    loading.value = false
  }
}

async function triggerSync() {
  syncing.value = true
  try {
    await axios.post(`/api/repos/${props.owner}/${props.repo}/sync`)
    syncVersion.value++
    await load()
  } finally {
    syncing.value = false
  }
}

onMounted(load)
watch(() => [props.owner, props.repo], load)
watch(() => [dateRange.since, dateRange.until, dateRange.coverageVersion], load)
</script>

<style scoped>
.stat-range {
  font-size: 0.75rem;
  color: #586069;
  margin-top: 0.25rem;
}
.title-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}
.title-bar h2 {
  margin: 0;
}
.title-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.sync-time {
  font-size: 0.8rem;
  color: #586069;
}
.sync-error {
  font-size: 0.8rem;
  color: #cb2431;
  cursor: help;
}
</style>
