<template>
  <div>
    <select v-model="selected" @change="navigate">
      <option value="">All Repositories</option>
      <option v-for="r in repos" :key="`${r.owner}/${r.name}`" :value="`${r.owner}/${r.name}`">
        {{ r.owner }}/{{ r.name }}
      </option>
    </select>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useReposStore } from '@/stores/repos'
import { storeToRefs } from 'pinia'

const router = useRouter()
const route = useRoute()
const reposStore = useReposStore()
const { repos } = storeToRefs(reposStore)
const selected = ref('')

watch(
  () => route.params,
  (params) => {
    if (params.owner && params.repo) {
      selected.value = `${params.owner}/${params.repo}`
    } else {
      selected.value = ''
    }
  },
  { immediate: true },
)

function navigate() {
  if (selected.value) {
    const [owner, repo] = selected.value.split('/')
    router.push({ name: 'repo-detail', params: { owner, repo } })
  } else {
    router.push({ name: 'home' })
  }
}
</script>

<style scoped>
select { padding: 0.3rem 0.5rem; border-radius: 4px; border: 1px solid #444d56; background: #2f363d; color: #fff; }
</style>
