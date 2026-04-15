<template>
  <div>
    <h2>Team Members</h2>

    <div class="card" style="margin-bottom: 1.5rem;">
      <h3>Common Members (all repos)</h3>
      <div class="member-list">
        <span v-for="m in commonMembers" :key="m" class="member-badge">
          <router-link :to="{ name: 'member-detail', params: { login: m } }">{{ m }}</router-link>
          <button class="remove-btn" @click="removeCommon(m)" title="Remove">&times;</button>
        </span>
        <span v-if="!commonMembers.length" class="muted">No common members configured</span>
      </div>
      <form @submit.prevent="addCommon" class="add-form">
        <input v-model="newCommon" placeholder="login1, login2, ..." />
        <button class="primary" type="submit" :disabled="!newCommon.trim()">Add</button>
      </form>
      <p v-if="commonError" class="error">{{ commonError }}</p>
    </div>

    <div v-for="r in repos" :key="`${r.owner}/${r.name}`" class="card" style="margin-bottom: 1rem;">
      <h3>{{ r.owner }}/{{ r.name }} — Supplemental Members</h3>
      <div class="member-list">
        <span v-for="m in repoMembers[`${r.owner}/${r.name}`] || []" :key="m" class="member-badge">
          <router-link :to="{ name: 'member-detail', params: { login: m } }">{{ m }}</router-link>
          <button class="remove-btn" @click="removeRepoMember(r.owner, r.name, m)" title="Remove">&times;</button>
        </span>
        <span v-if="!(repoMembers[`${r.owner}/${r.name}`] || []).length" class="muted">None (using common members only)</span>
      </div>
      <form @submit.prevent="addRepoMember(r.owner, r.name)" class="add-form">
        <input v-model="newRepoMember[`${r.owner}/${r.name}`]" placeholder="login1, login2, ..." />
        <button class="primary" type="submit" :disabled="!newRepoMember[`${r.owner}/${r.name}`]?.trim()">Add</button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'

interface RepoItem { owner: string; name: string }

const commonMembers = ref<string[]>([])
const repos = ref<RepoItem[]>([])
const repoMembers = ref<Record<string, string[]>>({})
const newCommon = ref('')
const newRepoMember = ref<Record<string, string>>({})
const commonError = ref<string | null>(null)

async function loadCommon() {
  const { data } = await axios.get('/api/team/common')
  commonMembers.value = data.members
}

async function loadRepos() {
  const { data } = await axios.get('/api/repos')
  repos.value = data.map((r: { owner: string; name: string }) => ({ owner: r.owner, name: r.name }))
  for (const r of repos.value) {
    const { data: tm } = await axios.get(`/api/team/repos/${r.owner}/${r.name}`)
    repoMembers.value[`${r.owner}/${r.name}`] = tm.repo_members
  }
}

function parseLogins(input: string): string[] {
  return input.split(/[,;]+/).map(s => s.trim()).filter(Boolean)
}

async function addCommon() {
  commonError.value = null
  const logins = parseLogins(newCommon.value)
  if (!logins.length) return
  try {
    for (const login of logins) {
      await axios.post('/api/team/common', { login })
    }
    newCommon.value = ''
    await loadCommon()
  } catch (e: unknown) {
    if (axios.isAxiosError(e) && e.response?.status === 409) {
      commonError.value = 'One or more already exist'
    } else {
      commonError.value = 'Failed to add'
    }
  }
}

async function removeCommon(login: string) {
  await axios.delete(`/api/team/common/${login}`)
  await loadCommon()
}

async function addRepoMember(owner: string, name: string) {
  const key = `${owner}/${name}`
  const logins = parseLogins(newRepoMember.value[key] || '')
  if (!logins.length) return
  try {
    for (const login of logins) {
      await axios.post(`/api/team/repos/${owner}/${name}`, { login })
    }
    newRepoMember.value[key] = ''
    const { data: tm } = await axios.get(`/api/team/repos/${owner}/${name}`)
    repoMembers.value[key] = tm.repo_members
  } catch { /* ignore duplicates */ }
}

async function removeRepoMember(owner: string, name: string, login: string) {
  await axios.delete(`/api/team/repos/${owner}/${name}/${login}`)
  const { data: tm } = await axios.get(`/api/team/repos/${owner}/${name}`)
  repoMembers.value[`${owner}/${name}`] = tm.repo_members
}

onMounted(async () => {
  await Promise.all([loadCommon(), loadRepos()])
})
</script>

<style scoped>
.member-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
.member-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.6rem;
  background: #e1e4e8;
  border-radius: 12px;
  font-size: 0.85rem;
}
.remove-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;
  color: #586069;
  padding: 0 0.15rem;
}
.remove-btn:hover {
  color: #cb2431;
}
.add-form {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.add-form input {
  padding: 0.4rem;
  border: 1px solid #e1e4e8;
  border-radius: 4px;
  width: 180px;
}
.muted { color: #586069; font-size: 0.85rem; }
.error { color: #cb2431; font-size: 0.85rem; margin-top: 0.25rem; }
</style>
