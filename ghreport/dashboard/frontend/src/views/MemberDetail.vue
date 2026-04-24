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
        <div class="card"><div class="stat">{{ summary.prs_created }}</div><div class="stat-label">PRs Opened</div></div>
        <div class="card"><div class="stat">{{ summary.prs_merged }}</div><div class="stat-label">PRs Merged</div></div>
        <div class="card"><div class="stat">{{ summary.prs_reviewed }}</div><div class="stat-label">PRs Reviewed</div></div>
        <div class="card"><div class="stat">{{ summary.prs_collaborated }}</div><div class="stat-label">PRs Collaborated</div></div>
        <div class="card"><div class="stat">{{ summary.total_lines_changed }}</div><div class="stat-label">Lines Changed</div></div>
      </div>

      <div v-if="loadingSummary" class="activity-summary">
        <span class="summary-loading">Generating activity summary…</span>
      </div>
      <div v-else-if="activitySummary" class="activity-summary">
        <span class="summary-label">Last {{ summaryPeriodDays }} days</span>
        {{ activitySummary }}
      </div>
      <div v-else-if="summaryError" class="activity-summary summary-error">
        Activity summary unavailable.
      </div>

      <div class="tab-buttons" style="margin-bottom: 1rem;">
        <button :class="{ active: activeTab === 'prs' }" @click="activeTab = 'prs'">PRs ({{ prs?.total || 0 }})</button>
        <button :class="{ active: activeTab === 'issues' }" @click="activeTab = 'issues'" style="margin-left: 0.5rem;">Issues ({{ issues?.total || 0 }})</button>
      </div>

      <div v-if="activeTab === 'prs' && prs">
        <div class="role-filter" style="margin-bottom: 0.75rem;">
          <button v-for="rf in roleFilters" :key="rf.value"
            :class="{ active: prRole === rf.value }" @click="prRole = rf.value">
            {{ rf.label }} ({{ rf.count }})
          </button>
        </div>
        <table v-if="filteredPrs.length">
          <thead><tr>
            <th class="sortable" @click="prSort.toggleSort('owner')">Repo{{ prSort.sortIndicator('owner') }}</th>
            <th class="sortable" @click="prSort.toggleSort('number')">#{{ prSort.sortIndicator('number') }}</th>
            <th class="sortable" @click="prSort.toggleSort('title')">Title{{ prSort.sortIndicator('title') }}</th>
            <th>Role</th>
            <th class="sortable" @click="prSort.toggleSort('state')">State{{ prSort.sortIndicator('state') }}</th>
            <th class="sortable" @click="prSort.toggleSort('created_at')">Created{{ prSort.sortIndicator('created_at') }}</th>
            <th class="sortable" @click="prSort.toggleSort('days_open')">Days{{ prSort.sortIndicator('days_open') }}</th>
            <th class="sortable" @click="prSort.toggleSort('lines_changed')">Lines{{ prSort.sortIndicator('lines_changed') }}</th>
          </tr></thead>
          <tbody>
            <tr v-for="pr in prSort.sorted.value" :key="`${pr.owner}/${pr.repo}/${pr.number}`">
              <td>{{ pr.owner }}/{{ pr.repo }}</td>
              <td><a :href="`https://github.com/${pr.owner}/${pr.repo}/pull/${pr.number}`" target="_blank">{{ pr.number }}</a></td>
              <td>{{ pr.title }}</td>
              <td>
                <span v-if="pr.is_author" class="role-tag author">Author</span>
                <span v-if="pr.is_reviewer" class="role-tag reviewer">Reviewer</span>
                <span v-if="pr.is_collaborator" class="role-tag collaborator">Collaborator</span>
              </td>
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
        <table v-if="issuesList.length">
          <thead><tr>
            <th class="sortable" @click="issueSort.toggleSort('owner')">Repo{{ issueSort.sortIndicator('owner') }}</th>
            <th class="sortable" @click="issueSort.toggleSort('number')">#{{ issueSort.sortIndicator('number') }}</th>
            <th class="sortable" @click="issueSort.toggleSort('title')">Title{{ issueSort.sortIndicator('title') }}</th>
            <th class="sortable" @click="issueSort.toggleSort('state')">State{{ issueSort.sortIndicator('state') }}</th>
            <th class="sortable" @click="issueSort.toggleSort('created_at')">Created{{ issueSort.sortIndicator('created_at') }}</th>
            <th>Role</th>
          </tr></thead>
          <tbody>
            <tr v-for="issue in issueSort.sorted.value" :key="`${issue.owner}/${issue.repo}/${issue.number}`">
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
import { ref, computed, onMounted, watch } from 'vue'
import axios from 'axios'
import { useDateRangeStore } from '@/stores/dateRange'
import { useSortable } from '@/composables/useSortable'

interface RepoItem { owner: string; name: string }

const props = defineProps<{ login: string }>()

const dateRange = useDateRangeStore()
const repos = ref<RepoItem[]>([])
const selectedRepo = ref('')
const activeTab = ref<'prs' | 'issues'>('prs')
const prRole = ref('')
const loading = ref(true)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const summary = ref<any>(null)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const prs = ref<any>(null)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const issues = ref<any>(null)
const activitySummary = ref<string | null>(null)
const summaryPeriodDays = ref<number>(14)
const loadingSummary = ref(false)
const summaryError = ref(false)

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

const filteredPrs = computed(() => {
  if (!prs.value?.prs) return []
  if (!prRole.value) return prs.value.prs
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return prs.value.prs.filter((pr: any) => {
    if (prRole.value === 'opened') return pr.is_author
    if (prRole.value === 'reviewed') return pr.is_reviewer
    if (prRole.value === 'collaborated') return pr.is_collaborator
    return true
  })
})

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const prSort = useSortable<any>(filteredPrs, 'created_at', 'desc')

const issuesList = computed(() => issues.value?.issues || [])
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const issueSort = useSortable<any>(issuesList, 'created_at', 'desc')

const roleFilters = computed(() => {
  const all = prs.value?.prs || []
  return [
    { label: 'All', value: '', count: all.length },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    { label: 'Opened', value: 'opened', count: all.filter((p: any) => p.is_author).length },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    { label: 'Reviewed', value: 'reviewed', count: all.filter((p: any) => p.is_reviewer).length },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    { label: 'Collaborated', value: 'collaborated', count: all.filter((p: any) => p.is_collaborator).length },
  ]
})

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

async function loadSummary() {
  loadingSummary.value = true
  activitySummary.value = null
  summaryError.value = false
  try {
    const { data } = await axios.get(`/api/members/${props.login}/activity-summary`)
    activitySummary.value = data.summary || null
    summaryPeriodDays.value = data.period_days ?? 14
  } catch {
    summaryError.value = true
  } finally {
    loadingSummary.value = false
  }
}

onMounted(async () => {
  const { data } = await axios.get('/api/repos')
  repos.value = data.map((r: { owner: string; name: string }) => ({ owner: r.owner, name: r.name }))
  await Promise.all([load(), loadSummary()])
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
.activity-summary {
  background: #f6f8fa;
  border: 1px solid #e1e4e8;
  border-left: 3px solid #0366d6;
  border-radius: 4px;
  padding: 0.75rem 1rem;
  margin-bottom: 1.25rem;
  font-size: 0.9rem;
  line-height: 1.5;
  color: #24292e;
}
.summary-loading {
  color: #586069;
  font-style: italic;
}
.summary-label {
  display: block;
  font-size: 0.75rem;
  font-weight: 600;
  color: #586069;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 0.35rem;
}
.summary-error {
  color: #586069;
  font-style: italic;
  border-left-color: #e1e4e8;
}
.role-tag {
  display: inline-block;
  font-size: 0.75rem;
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  background: #e1e4e8;
  margin-right: 0.25rem;
}
.role-tag.author { background: #0366d6; color: #fff; }
.role-tag.reviewer { background: #28a745; color: #fff; }
.role-tag.collaborator { background: #6f42c1; color: #fff; }
.role-filter {
  display: flex;
  gap: 0.35rem;
}
.role-filter button {
  padding: 0.3rem 0.75rem;
  border: 1px solid #e1e4e8;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  font-size: 0.85rem;
}
.role-filter button.active {
  background: #0366d6;
  color: #fff;
  border-color: #0366d6;
}
.badge { font-size: 0.8rem; padding: 0.1rem 0.5rem; border-radius: 10px; }
.badge.open { background: #28a745; color: #fff; }
.badge.closed { background: #cb2431; color: #fff; }
.badge.merged { background: #6f42c1; color: #fff; }
</style>
