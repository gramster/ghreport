<template>
  <div>
    <table v-if="data.terms?.length">
      <thead><tr><th>Term</th><th>Count</th></tr></thead>
      <tbody>
        <tr v-for="t in data.terms.slice(0, 30)" :key="t.term">
          <td>
            <a v-if="owner && repo" class="term-link"
              :href="`https://github.com/${owner}/${repo}/issues?q=is%3Aissue+${encodeURIComponent(t.term)}`"
              target="_blank" rel="noopener">{{ t.term }}</a>
            <span v-else>{{ t.term }}</span>
          </td>
          <td>
            <span class="bar" :style="{ width: `${(t.count / maxCount) * 100}%` }">
              {{ t.count }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else style="color: #586069;">No terms found</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  data: { terms: { term: string; count: number; issue_numbers: number[] }[] }
  owner?: string
  repo?: string
}>()

const maxCount = computed(() =>
  props.data.terms?.length ? Math.max(...props.data.terms.map(t => t.count)) : 1,
)
</script>

<style scoped>
.bar { display: inline-block; background: #0366d6; color: #fff; padding: 0.1rem 0.4rem; border-radius: 3px; font-size: 0.8rem; min-width: 20px; }
.term-link { color: inherit; text-decoration: none; }
.term-link:hover { text-decoration: underline; color: #0366d6; }
</style>
