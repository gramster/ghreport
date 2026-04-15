<template>
  <div>
    <h2>Member: {{ login }}</h2>

    <div class="filters">
      <label>Repo:
        <select v-model="selectedRepo">
          <option value="">All repos</option>
          <option v-for="r in repos" :key="`${r.owner}/${r.name}`" :value="`${r.owner}/${r.name}`">
            {{ r.owner }}/{{ r.name }}
          </option>
        </select>
      </label>
    </div>

    <div v-if="loading" class="loading">Loading...</div>
    <template v-else>
      <div v-if="summary" class="grid" style="margin-bottom: 1.5rem;">
        <div class="card"><div class="stat">{{ summary.issues_created }}</div><div class="stat-label">Issues Created</div></div>
        <div class="card"><div class="stat">{{ summary.issues_commented }}</div><div class="stat-label">Issues Commented</div></div>
        <div class="card"><div class="stat">{{ summary.prs_created }}</div><div class="stat-label">PRs Created</div></div>
        <div class="card"><div class="stat">{{ summary.prs_merged }}</div><div class="stat-label">PRs Merged</div></div>
        <div class="card"><div class="stat">{{ summary.total_lines_changed }}</div><div class="stat-label">Lines Changed</div></div>
      </div>

      <div class="tab-buttons" style="margin-bottom: 1rem;">
        <button :class="{ active: activeTab === 'prs' }" @click="activeTab = 'prs'">PRs ({{ prs?.total || 0 }})</button>
        <button :class="{ active: activeTab === 'issues' }" @click="activeTab = 'issues'" style="margin-left: 0.5rem;">Issues ({{ issues?.total || 0 }})</button>
      </div>

      <div v-if="activeTab === 'prs' && prs">
        <table v-if="prs.prs.length">
          <thead><tr><th>Repo</th><th>#</th><th>Title</th><th>State</th><th>Created</th><th>Days</th><th>Lines</th></tr></thead>
          <tbody>
            <tr v-for="pr in prs.prs" :key="`${pr.owner}/${pr.repo}/${pr.number}`">
              <td>{{ pr.owner }}/{{ pr.repo }}</td>
              <td><a :href="`https://github.com/${pr.owner}/${pr.repo}/pull/${pr.number}`" target="_blank">{{ pr.number }}</a></td>
              <td>{{ pr.title }}</td>
              <td><span :class="'badge ' + pr.state">{{ pr.state }}</span></td>
              <td>{{ pr.created_at }}</td>
              <td>{{ pr.days_open }}</td>
              <td>{{ pr.lines_changed }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted">No PRs found</p>
      </div>

      <div v-if="activeTab === 'issues' && issues">
        <table v-if="issues.issues.length">
          <thead><tr><th>Repo</th><th>#</th><th>Title</th><th>State</th><th>Created</th><th>Role</th></tr></thead>
          <tbody>
            <tr v-for="issue in issues.issues" :key="`${issue.owner}/${issue.repo}/${issue.number}`">
              <td>{{ issue.owner }}/{{ issue.repo }}</td>
              <td><a :href="`https://github.com/${issue.owner}/${issue.repo}/issues/${issue.number}`" target="_blank">{{ issue.number }}</a></td>
              <td>{{ issue.title }}</td>
              <td><span :class="'badge ' + issue.state">{{ issue.state }}</span></td>
              <td>{{ issue.created_at }}</td>
              <td>
                <span v-if="issue.is_author" class="role-tag">Author</span>
                <span v-if="issue.commented" class="role-tag">Commenter</span>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted">No issues found</p>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import axios from 'axios'
import { useDateRangeStore } from '@/stores/dateRange'

interface RepoItem { owner: string; name: string }

const props = defineProps<{ login: string }>()

const dateRange = useDateRangeStore()
const repos = ref<RepoItem[]>([])
const selectedRepo = ref('')
const activeTab = ref<'prs' | 'issues'>('prs')
const loading = ref(true)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const summary = ref<any>(null)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const prs = ref<any>(null)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const issues = ref<any>(null)

function buildParams() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const p: any = { ...dateRange.params }
  if (selectedRepo.value) {
    const [o, r] = selectedRepo.value.split('/')
    p.owner = o
    p.repo = r
  }
  return p
}

async function load() {
  loading.value = true
  try {
    const params = buildParams()
    const [s, p, i] = await Promise.all([
      axios.get(`/api/members/${props.login}/summary`, { params }),
      axios.get(`/api/members/${props.login}/prs`, { params }),
      axios.get(`/api/members/${props.login}/issues`, { params }),
    ])
    summary.value = s.data
    prs.value = p.data
    issues.value = i.data
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  const { data } = await axios.get('/api/repos')
  repos.value = data.map((r: { owner: string; name: string }) => ({ owner: r.owner, name: r.name }))
  await load()
})

watch([selectedRepo, () => dateRange.since, () => dateRange.until, () => dateRange.coverageVersion], load)
</script>

<style scoped>
.filters {
  display: flex;
  gap: 1rem;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 1rem;
}
.filters label {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}
.filters input, .filters select {
  padding: 0.35rem;
  border: 1px solid #e1e4e8;
  border-radius: 4px;
}
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
.muted { color: #586069; }
.role-tag {
  display: inline-block;
  font-size: 0.75rem;
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  background: #e1e4e8;
  margin-right: 0.25rem;
}
.badge { font-size: 0.8rem; padding: 0.1rem 0.5rem; border-radius: 10px; }
.badge.open { background: #28a745; color: #fff; }
.badge.closed { background: #cb2431; color: #fff; }
.badge.merged { background: #6f42c1; color: #fff; }
</style>
