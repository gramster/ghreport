<template>
  <div>
    <h2>{{ owner }}/{{ repo }} — AI Insights</h2>
    <div class="tabs">
      <router-link :to="{ name: 'repo-detail', params: { owner, repo } }">Overview</router-link>
      <router-link :to="{ name: 'issue-revisits', params: { owner, repo } }">Revisits</router-link>
      <router-link :to="{ name: 'pr-activity', params: { owner, repo } }">PR Activity</router-link>
      <router-link :to="{ name: 'closed-issues', params: { owner, repo } }">Closed Issues</router-link>
      <router-link :to="{ name: 'insights', params: { owner, repo } }">Insights</router-link>
    </div>

    <div class="tab-buttons" style="margin-bottom: 1rem;">
      <button :class="{ active: activeTab === 'digest' }" @click="activeTab = 'digest'">Activity Digest</button>
      <button :class="{ active: activeTab === 'anomalies' }" @click="activeTab = 'anomalies'" style="margin-left: 0.5rem;">Anomaly Detection</button>
      <button :class="{ active: activeTab === 'clusters' }" @click="switchToClusters" style="margin-left: 0.5rem;">Issue Clusters</button>
    </div>

    <!-- Activity Digest -->
    <div v-if="activeTab === 'digest'">
      <div class="card insight-card">
        <div class="insight-header">
          <h3>Activity Digest</h3>
          <button class="primary" @click="loadDigest" :disabled="digestLoading">
            {{ digestLoading ? 'Generating...' : (digest ? 'Regenerate' : 'Generate') }}
          </button>
        </div>
        <div v-if="digestLoading" class="loading">
          <span class="spinner">↻</span> Analyzing repository activity...
        </div>
        <div v-else-if="digest" class="insight-content" v-html="renderMd(digest)"></div>
        <p v-else-if="digestError" class="error-text">{{ digestError }}</p>
        <p v-else class="hint-text">Click Generate to create an AI-powered activity summary.</p>
      </div>
    </div>

    <!-- Anomaly Detection -->
    <div v-if="activeTab === 'anomalies'">
      <div class="card insight-card">
        <div class="insight-header">
          <h3>Anomaly Detection</h3>
          <button class="primary" @click="loadAnomalies" :disabled="anomaliesLoading">
            {{ anomaliesLoading ? 'Analyzing...' : (anomalies ? 'Re-analyze' : 'Analyze') }}
          </button>
        </div>
        <p class="hint-text" style="margin-bottom: 0.5rem;">
          Compares recent {{ anomalyDays }}-day period against the prior {{ anomalyDays * 3 }}-day baseline.
        </p>
        <div v-if="anomaliesLoading" class="loading">
          <span class="spinner">↻</span> Comparing metrics against baseline...
        </div>
        <div v-else-if="anomalies" class="insight-content" v-html="renderMd(anomalies)"></div>
        <p v-else-if="anomaliesError" class="error-text">{{ anomaliesError }}</p>
      </div>
    </div>

    <!-- Issue Clusters -->
    <div v-if="activeTab === 'clusters'">
      <div class="card insight-card">
        <div class="insight-header">
          <h3>Issue Clusters</h3>
          <button class="primary" @click="loadClusters(true)" :disabled="clustersLoading">
            {{ clustersLoading ? 'Clustering...' : 'Re-cluster' }}
          </button>
        </div>
        <div v-if="clustersLoading" class="loading">
          <span class="spinner">↻</span> Grouping issues by topic...
        </div>
        <template v-else-if="clusters && clusters.length > 0">
          <p class="hint-text" style="margin-bottom: 0.75rem;">{{ totalIssues }} open issues grouped into {{ clusters.length }} clusters<span v-if="fromCache"> (cached)</span></p>
          <ClusterNode
            v-for="(cluster, idx) in clusters"
            :key="idx"
            :cluster="cluster"
            :owner="owner"
            :repo="repo"
            :issue-titles="issueTitles"
            :level="0"
          />
        </template>
        <p v-else-if="clusters && clusters.length === 0" class="hint-text">No open issues to cluster.</p>
        <p v-else-if="clustersError" class="error-text">{{ clustersError }}</p>
        <div v-else class="loading">
          <span class="spinner">↻</span> Loading cached clusters...
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import axios from 'axios'
import { useDateRangeStore } from '@/stores/dateRange'
import ClusterNode from '@/components/ClusterNode.vue'

interface Cluster {
  name: string
  issues: number[]
  summary: string
  subclusters?: Cluster[]
}

type IssueTitleMap = Record<number, string>

const props = defineProps<{ owner: string; repo: string }>()
const dateRange = useDateRangeStore()

const activeTab = ref<'digest' | 'anomalies' | 'clusters'>('digest')

// Digest state
const digest = ref<string | null>(null)
const digestLoading = ref(false)
const digestError = ref('')

// Anomalies state
const anomalies = ref<string | null>(null)
const anomaliesLoading = ref(false)
const anomaliesError = ref('')
const anomalyDays = computed(() => {
  if (dateRange.since && dateRange.until) {
    const diff = new Date(dateRange.until).getTime() - new Date(dateRange.since).getTime()
    return Math.max(1, Math.round(diff / (1000 * 60 * 60 * 24)))
  }
  return 14
})

// Clusters state
const clusters = ref<Cluster[] | null>(null)
const issueTitles = ref<IssueTitleMap>({})
const totalIssues = ref(0)
const clustersLoading = ref(false)
const clustersError = ref('')
const fromCache = ref(false)

function renderMd(text: string): string {
  // Minimal markdown: bold, bullets, inline code
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/^[-•] (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
    .replace(/<\/ul>\s*<ul>/g, '')
    .replace(/\n/g, '<br>')
}

async function loadDigest() {
  digestLoading.value = true
  digestError.value = ''
  try {
    const { data } = await axios.get(`/api/repos/${props.owner}/${props.repo}/insights/digest`, {
      params: dateRange.params,
    })
    digest.value = data.digest
  } catch (e: any) {
    digestError.value = e.response?.data?.detail || 'Failed to generate digest'
  } finally {
    digestLoading.value = false
  }
}

async function loadAnomalies() {
  anomaliesLoading.value = true
  anomaliesError.value = ''
  try {
    const { data } = await axios.get(`/api/repos/${props.owner}/${props.repo}/insights/anomalies`, {
      params: dateRange.params,
    })
    anomalies.value = data.anomalies
  } catch (e: any) {
    anomaliesError.value = e.response?.data?.detail || 'Failed to detect anomalies'
  } finally {
    anomaliesLoading.value = false
  }
}

async function loadClusters(force = false) {
  clustersLoading.value = true
  clustersError.value = ''
  try {
    const { data } = await axios.get(`/api/repos/${props.owner}/${props.repo}/insights/clusters`, {
      params: force ? { force: true } : {},
    })
    clusters.value = data.clusters
    issueTitles.value = data.issue_titles || {}
    totalIssues.value = data.total_issues
    fromCache.value = !!data.from_cache
  } catch (e: any) {
    clustersError.value = e.response?.data?.detail || 'Failed to cluster issues'
  } finally {
    clustersLoading.value = false
  }
}

function switchToClusters() {
  activeTab.value = 'clusters'
  if (!clusters.value) {
    loadClusters(false)
  }
}
</script>

<style scoped>
.insight-card {
  margin-bottom: 1.5rem;
}
.insight-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}
.insight-header h3 {
  margin: 0;
}
.insight-content {
  line-height: 1.6;
}
.insight-content :deep(ul) {
  margin: 0.5rem 0;
  padding-left: 1.5rem;
}
.insight-content :deep(li) {
  margin-bottom: 0.4rem;
}
.insight-content :deep(code) {
  background: #f0f0f0;
  padding: 0.1em 0.3em;
  border-radius: 3px;
  font-size: 0.9em;
}
.hint-text {
  color: #586069;
  font-style: italic;
}
.error-text {
  color: #cb2431;
}
.spinner {
  display: inline-block;
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
