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
      <div v-for="(sectionKey, idx) in ['bugs', 'non_bugs']" :key="idx">
        <h3>{{ sectionKey === 'bugs' ? 'Bug Issues' : 'Non-Bug Issues' }}</h3>
        <div v-for="(catKey, ci) in ['needs_response', 'op_responded', 'third_party_responded', 'stale']" :key="ci">
          <h4 style="margin-top: 0.75rem;">{{ formatCat(catKey) }} ({{ data.sections[sectionKey]?.[catKey]?.length || 0 }})</h4>
          <table v-if="data.sections[sectionKey]?.[catKey]?.length">
            <thead><tr><th>#</th><th>Title</th><th>Created By</th><th>Created</th><th></th></tr></thead>
            <tbody>
              <tr v-for="issue in data.sections[sectionKey][catKey]" :key="issue.number">
                <td>{{ issue.number }}</td>
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

const props = defineProps<{ owner: string; repo: string }>()
const data = ref<Record<string, unknown> | null>(null)
const loading = ref(true)

function formatCat(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

async function load() {
  loading.value = true
  try {
    const { data: d } = await axios.get(`/api/repos/${props.owner}/${props.repo}/reports/revisits`, {
      params: { show_all: true },
    })
    data.value = d
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => [props.owner, props.repo], load)
</script>
