<template>
  <div>
    <h2>{{ owner }}/{{ repo }} — Issue Revisits</h2>
    <div class="tabs">
      <router-link :to="{ name: 'repo-detail', params: { owner, repo } }">Overview</router-link>
      <router-link :to="{ name: 'issue-revisits', params: { owner, repo } }">Revisits</router-link>
      <router-link :to="{ name: 'pr-activity', params: { owner, repo } }">PR Activity</router-link>
      <router-link :to="{ name: 'closed-issues', params: { owner, repo } }">Closed Issues</router-link>
    </div>

    <div v-if="loading" class="loading">Loading...</div>
    <template v-else-if="data">
      <div class="tab-buttons" style="margin-bottom: 1rem;">
        <button :class="{ active: activeTab === 'bugs' }" @click="activeTab = 'bugs'">Bugs</button>
        <button :class="{ active: activeTab === 'non_bugs' }" @click="activeTab = 'non_bugs'" style="margin-left: 0.5rem;">Non-Bugs</button>
      </div>
      <div v-for="(sectionKey, idx) in [activeTab]" :key="idx">
        <h3>{{ sectionKey === 'bugs' ? 'Bug Issues' : 'Non-Bug Issues' }}</h3>
        <div v-for="(catKey, ci) in ['needs_response', 'op_responded', 'third_party_responded', 'stale']" :key="ci">
          <h4 style="margin-top: 0.75rem;">{{ formatCat(catKey) }} ({{ data.sections[sectionKey]?.[catKey]?.length || 0 }})</h4>
          <table v-if="data.sections[sectionKey]?.[catKey]?.length">
            <thead><tr><th>#</th><th>Title</th><th>Created By</th><th>Created</th><th></th></tr></thead>
            <tbody>
              <tr v-for="issue in data.sections[sectionKey][catKey]" :key="issue.number">
                <td><a :href="`https://github.com/${owner}/${repo}/issues/${issue.number}`" target="_blank">{{ issue.number }}</a></td>
                <td>{{ issue.title }}</td>
                <td>{{ issue.created_by }}</td>
                <td>{{ issue.created_at }}</td>
                <td><span v-if="issue.star" class="star">★</span></td>
              </tr>
            </tbody>
          </table>
          <p v-else style="color: #586069; margin-left: 1rem;">None</p>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import axios from 'axios'
import { useDateRangeStore } from '@/stores/dateRange'

interface RevisitIssue {
  number: number; title: string; created_by: string; created_at: string; star: boolean
  days_op?: number; days_team?: number; days_third_party?: number
}

interface RevisitsData {
  sections: Record<string, Record<string, RevisitIssue[]>>
}

const props = defineProps<{ owner: string; repo: string }>()
const dateRange = useDateRangeStore()
const data = ref<RevisitsData | null>(null)
const loading = ref(true)
const activeTab = ref<'bugs' | 'non_bugs'>('bugs')

function formatCat(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

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
.tab-buttons button {
  padding: 0.4rem 1rem;
  border: 1px solid #e1e4e8;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
}
.tab-buttons button.active {
  background: #0366d6;
  color: #fff;
  border-color: #0366d6;
}
</style>
