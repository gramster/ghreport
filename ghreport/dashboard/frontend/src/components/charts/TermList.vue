<template>
  <div>
    <table v-if="data.terms?.length">
      <thead><tr><th>Term</th><th>Count</th></tr></thead>
      <tbody>
        <tr v-for="t in data.terms.slice(0, 30)" :key="t.term">
          <td>{{ t.term }}</td>
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
}>()

const maxCount = computed(() =>
  props.data.terms?.length ? Math.max(...props.data.terms.map(t => t.count)) : 1,
)
</script>

<style scoped>
.bar { display: inline-block; background: #0366d6; color: #fff; padding: 0.1rem 0.4rem; border-radius: 3px; font-size: 0.8rem; min-width: 20px; }
</style>
