<template>
  <div id="app">
    <nav class="navbar">
      <router-link to="/" class="brand">ghreport</router-link>
      <router-link to="/repos" class="nav-link">Repos</router-link>
      <router-link to="/team" class="nav-link">Team</router-link>
      <div class="nav-dates">
        <label>Since <input type="date" v-model="dateRange.since" /></label>
        <label>Until <input type="date" v-model="dateRange.until" /></label>
        <span v-if="dateRange.backfilling" class="sync-indicator" title="Fetching older data...">⟳</span>
        <span v-else-if="syncActivity.syncing.length" class="sync-indicator"
              :title="'Syncing: ' + syncActivity.syncing.join(', ')">⟳</span>
      </div>
      <RepoSelector />
    </nav>
    <div v-if="syncActivity.syncing.length" class="activity-banner">
      <div class="activity-banner-content">
        <span class="sync-indicator-inline">⟳</span>
        <span>Syncing: {{ syncActivity.syncing.join(', ') }}</span>
      </div>
    </div>
    <div v-if="syncActivity.errors.length" class="error-banner">
      <div class="error-banner-content">
        <span class="error-icon">⚠</span>
        <span>{{ syncActivity.errors.length }} sync error{{ syncActivity.errors.length > 1 ? 's' : '' }}:
          <span class="error-detail">{{ latestError }}</span>
        </span>
        <button class="error-dismiss" @click="syncActivity.dismissErrors()" title="Dismiss">✕</button>
      </div>
    </div>
    <main class="content">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import RepoSelector from '@/components/RepoSelector.vue'
import { useReposStore } from '@/stores/repos'
import { useDateRangeStore } from '@/stores/dateRange'
import { useSyncActivityStore } from '@/stores/syncActivity'
import { onMounted, onUnmounted, computed } from 'vue'

const reposStore = useReposStore()
const dateRange = useDateRangeStore()
const syncActivity = useSyncActivityStore()

const latestError = computed(() => {
  if (!syncActivity.errors.length) return ''
  const last = syncActivity.errors[syncActivity.errors.length - 1]
  return `${last.repo}: ${last.error}`
})

onMounted(() => {
  reposStore.fetchRepos()
  syncActivity.startPolling()
})
onUnmounted(() => syncActivity.stopPolling())
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; }
.navbar { display: flex; align-items: center; gap: 1rem; padding: 0.75rem 1.5rem; background: #24292e; color: #fff; }
.navbar .brand { color: #fff; text-decoration: none; font-size: 1.25rem; font-weight: 600; }
.nav-link { color: #ffffffcc; text-decoration: none; font-size: 0.9rem; }
.nav-link:hover { color: #fff; }
.nav-dates { display: flex; gap: 0.75rem; align-items: center; margin-left: auto; }
.nav-dates label { display: flex; align-items: center; gap: 0.3rem; color: #ffffffcc; font-size: 0.85rem; }
.nav-dates input { padding: 0.25rem 0.4rem; border: 1px solid #586069; border-radius: 4px; background: #2f363d; color: #fff; font-size: 0.85rem; }
.sync-indicator { animation: spin 1s linear infinite; font-size: 1.1rem; color: #f9826c; }
@keyframes spin { to { transform: rotate(360deg); } }
.activity-banner { background: #dcffe4; border-bottom: 1px solid #34d058; padding: 0.5rem 1.5rem; }
.activity-banner-content { display: flex; align-items: center; gap: 0.5rem; max-width: 1200px; margin: 0 auto; font-size: 0.9rem; color: #165c26; }
.sync-indicator-inline { animation: spin 1s linear infinite; font-size: 1rem; }
.error-banner { background: #ffeef0; border-bottom: 1px solid #fdaeb7; padding: 0.5rem 1.5rem; }
.error-banner-content { display: flex; align-items: center; gap: 0.5rem; max-width: 1200px; margin: 0 auto; font-size: 0.9rem; color: #86181d; }
.error-icon { font-size: 1.1rem; }
.error-detail { color: #cb2431; font-family: monospace; font-size: 0.82rem; }
.error-dismiss { background: none; border: none; color: #86181d; cursor: pointer; font-size: 1rem; margin-left: auto; padding: 0.2rem 0.4rem; }
.error-dismiss:hover { color: #cb2431; }
.content { max-width: 1200px; margin: 1.5rem auto; padding: 0 1rem; }
a { color: #0366d6; }
table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
th, td { text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid #e1e4e8; }
th { background: #f6f8fa; font-weight: 600; }
th.sortable { cursor: pointer; user-select: none; }
th.sortable:hover { background: #ebedf0; }
.card { background: #fff; border: 1px solid #e1e4e8; border-radius: 6px; padding: 1rem 1.25rem; margin-bottom: 1rem; }
.card h3 { margin-bottom: 0.5rem; }
.stat { font-size: 2rem; font-weight: 700; }
.stat-label { font-size: 0.85rem; color: #586069; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; }
.tabs { display: flex; gap: 0; border-bottom: 2px solid #e1e4e8; margin-bottom: 1rem; }
.tabs a { padding: 0.5rem 1rem; text-decoration: none; color: #586069; border-bottom: 2px solid transparent; margin-bottom: -2px; }
.tabs a.router-link-active, .tabs a:hover { color: #24292e; border-bottom-color: #f9826c; }
button { padding: 0.4rem 0.8rem; border: 1px solid #e1e4e8; border-radius: 4px; background: #fafbfc; cursor: pointer; }
button:hover { background: #f3f4f6; }
button.primary { background: #2ea44f; color: #fff; border-color: #2ea44f; }
button.primary:hover { background: #2c974b; }
button.danger { background: #cb2431; color: #fff; border-color: #cb2431; font-size: 0.8rem; }
button.danger:hover { background: #a3202a; }
.badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 10px; font-size: 0.75rem; font-weight: 600; }
.badge.open { background: #2ea44f; color: #fff; }
.badge.closed { background: #6f42c1; color: #fff; }
.badge.merged { background: #6f42c1; color: #fff; }
.star { color: #f0ad4e; }
.loading { text-align: center; padding: 2rem; color: #586069; }
</style>
