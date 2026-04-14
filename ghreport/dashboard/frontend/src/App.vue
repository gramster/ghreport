<template>
  <div id="app">
    <nav class="navbar">
      <router-link to="/" class="brand">ghreport</router-link>
      <RepoSelector />
    </nav>
    <main class="content">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import RepoSelector from '@/components/RepoSelector.vue'
import { useReposStore } from '@/stores/repos'
import { onMounted } from 'vue'

const reposStore = useReposStore()
onMounted(() => reposStore.fetchRepos())
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; }
.navbar { display: flex; align-items: center; gap: 1rem; padding: 0.75rem 1.5rem; background: #24292e; color: #fff; }
.navbar .brand { color: #fff; text-decoration: none; font-size: 1.25rem; font-weight: 600; }
.content { max-width: 1200px; margin: 1.5rem auto; padding: 0 1rem; }
a { color: #0366d6; }
table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
th, td { text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid #e1e4e8; }
th { background: #f6f8fa; font-weight: 600; }
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
.badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 10px; font-size: 0.75rem; font-weight: 600; }
.badge.open { background: #2ea44f; color: #fff; }
.badge.closed { background: #6f42c1; color: #fff; }
.badge.merged { background: #6f42c1; color: #fff; }
.star { color: #f0ad4e; }
.loading { text-align: center; padding: 2rem; color: #586069; }
</style>
