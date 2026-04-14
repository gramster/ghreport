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
          <button class="danger" style="margin-top: 0.5rem;" @click="removeRepo(r.owner, r.name)">Remove</button>
        </div>

        <div class="card add-repo-card">
          <h3>Add Repository</h3>
          <form @submit.prevent="addRepo" style="display: flex; flex-direction: column; gap: 0.5rem;">
            <input v-model="newRepo" placeholder="owner/repo" style="padding: 0.4rem; border: 1px solid #e1e4e8; border-radius: 4px;" />
            <button class="primary" type="submit" :disabled="!newRepo.includes('/')">Add</button>
            <p v-if="addError" style="color: #cb2431; font-size: 0.85rem;">{{ addError }}</p>
          </form>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { useReposStore } from '@/stores/repos'

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

const reposStore = useReposStore()
const summary = ref<AggSummary | null>(null)
const loading = ref(true)
const newRepo = ref('')
const addError = ref<string | null>(null)

async function load() {
  loading.value = true
  try {
    const { data } = await axios.get<AggSummary>('/api/aggregate/summary')
    summary.value = data
  } finally {
    loading.value = false
  }
}

async function addRepo() {
  addError.value = null
  const parts = newRepo.value.trim().split('/')
  if (parts.length !== 2 || !parts[0] || !parts[1]) {
    addError.value = 'Enter as owner/repo'
    return
  }
  try {
    await reposStore.addRepo(parts[0], parts[1])
    newRepo.value = ''
    await load()
  } catch (e: unknown) {
    if (axios.isAxiosError(e) && e.response?.status === 409) {
      addError.value = 'Repository already added'
    } else {
      addError.value = 'Failed to add repository'
    }
  }
}

async function removeRepo(owner: string, name: string) {
  if (!confirm(`Remove ${owner}/${name} and all its cached data?`)) return
  try {
    await reposStore.removeRepo(owner, name)
    await load()
  } catch {
    alert('Failed to remove repository')
  }
}

onMounted(load)
</script>
