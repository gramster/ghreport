<template>
  <div>
    <h2>{{ owner }}/{{ repo }}</h2>
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
        </div>
        <div class="card">
          <div class="stat">{{ repoInfo.issues?.closed || 0 }}</div>
          <div class="stat-label">Closed Issues</div>
        </div>
        <div class="card">
          <div class="stat">{{ repoInfo.pull_requests?.open || 0 }}</div>
          <div class="stat-label">Open PRs</div>
        </div>
        <div class="card">
          <div class="stat">{{ repoInfo.pull_requests?.merged || 0 }}</div>
          <div class="stat-label">Merged PRs</div>
        </div>
      </div>

      <div class="card">
        <h3>Actions</h3>
        <button class="primary" @click="triggerSync" :disabled="syncing">
          {{ syncing ? 'Syncing...' : 'Sync Now' }}
        </button>
        <span v-if="repoInfo.last_synced_at" style="margin-left: 1rem; color: #586069;">
          Last synced: {{ new Date(repoInfo.last_synced_at).toLocaleString() }}
        </span>
      </div>

      <h3 style="margin-top: 1rem;">Charts</h3>
      <div class="grid">
        <ChartCard title="Open Issues" :owner="owner" :repo="repo" chart-type="open-issues" />
        <ChartCard title="Time to Merge" :owner="owner" :repo="repo" chart-type="time-to-merge" />
        <ChartCard title="Time to Close" :owner="owner" :repo="repo" chart-type="time-to-close" />
        <ChartCard title="Time to Response" :owner="owner" :repo="repo" chart-type="time-to-response" />
        <ChartCard title="Label Frequency" :owner="owner" :repo="repo" chart-type="label-frequency" />
        <ChartCard title="Files Changed/PR" :owner="owner" :repo="repo" chart-type="files-changed" />
        <ChartCard title="Lines Changed/PR" :owner="owner" :repo="repo" chart-type="lines-changed" />
        <ChartCard title="Top Terms" :owner="owner" :repo="repo" chart-type="top-terms" />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import axios from 'axios'
import ChartCard from '@/components/ChartCard.vue'

const props = defineProps<{ owner: string; repo: string }>()
const repoInfo = ref<Record<string, unknown> | null>(null)
const loading = ref(true)
const syncing = ref(false)

async function load() {
  loading.value = true
  try {
    const { data } = await axios.get(`/api/repos/${props.owner}/${props.repo}`)
    repoInfo.value = data
  } finally {
    loading.value = false
  }
}

async function triggerSync() {
  syncing.value = true
  try {
    await axios.post(`/api/repos/${props.owner}/${props.repo}/sync`)
    await load()
  } finally {
    syncing.value = false
  }
}

onMounted(load)
watch(() => [props.owner, props.repo], load)
</script>
