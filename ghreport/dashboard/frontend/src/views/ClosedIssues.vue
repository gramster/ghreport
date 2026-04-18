<template>
  <div>
    <h2>{{ owner }}/{{ repo }} — Recently Closed Issues</h2>
    <div class="tabs">
      <router-link :to="{ name: 'repo-detail', params: { owner, repo } }">Overview</router-link>
      <router-link :to="{ name: 'issue-revisits', params: { owner, repo } }">Revisits</router-link>
      <router-link :to="{ name: 'pr-activity', params: { owner, repo } }">PR Activity</router-link>
      <router-link :to="{ name: 'closed-issues', params: { owner, repo } }">Closed Issues</router-link>
      <router-link :to="{ name: 'insights', params: { owner, repo } }">Insights</router-link>
    </div>

    <div v-if="loading" class="loading">Loading...</div>
    <template v-else-if="data">
      <p>{{ data.issues?.length || 0 }} issues closed in window</p>
      <table v-if="data.issues?.length">
        <thead><tr>
          <th class="sortable" @click="sort.toggleSort('number')">#{{ sort.sortIndicator('number') }}</th>
          <th class="sortable" @click="sort.toggleSort('title')">Title{{ sort.sortIndicator('title') }}</th>
          <th class="sortable" @click="sort.toggleSort('created_by')">By{{ sort.sortIndicator('created_by') }}</th>
          <th class="sortable" @click="sort.toggleSort('closed_at')">Closed{{ sort.sortIndicator('closed_at') }}</th>
          <th class="sortable" @click="sort.toggleSort('closed_by')">Closed By{{ sort.sortIndicator('closed_by') }}</th>
          <th class="sortable" @click="sort.toggleSort('days_open')">Days Open{{ sort.sortIndicator('days_open') }}</th>
        </tr></thead>
        <tbody>
          <tr v-for="issue in sort.sorted.value" :key="issue.number">
            <td><a :href="`https://github.com/${owner}/${repo}/issues/${issue.number}`" target="_blank">{{ issue.number }}</a></td>
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
import { ref, computed, onMounted, watch } from 'vue'
import axios from 'axios'
import { useDateRangeStore } from '@/stores/dateRange'
import { useSortable } from '@/composables/useSortable'

interface ClosedIssue {
  number: number; title: string; created_by: string
  closed_at: string | null; closed_by: string | null; days_open: number
}

interface ClosedIssuesData {
  issues: ClosedIssue[]
}

const dateRange = useDateRangeStore()
const props = defineProps<{ owner: string; repo: string }>()
const data = ref<ClosedIssuesData | null>(null)
const loading = ref(true)

const issueList = computed(() => data.value?.issues || [])
const sort = useSortable(issueList, 'closed_at', 'desc')

async function load() {
  loading.value = true
  try {
    const params: Record<string, string | number> = {
      days: dateRange.effectiveDays, ...dateRange.params,
    }
    const { data: d } = await axios.get(
      `/api/repos/${props.owner}/${props.repo}/reports/closed-issues`,
      { params },
    )
    data.value = d
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => [props.owner, props.repo], load)
watch(() => [dateRange.since, dateRange.until, dateRange.coverageVersion], load)
</script>
