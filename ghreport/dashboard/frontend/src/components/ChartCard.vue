<template>
  <div class="card">
    <h3>{{ title }}</h3>
    <div v-if="loading" class="loading">Loading...</div>
    <div v-else-if="error" style="color: #cb2431;">{{ error }}</div>
    <template v-else>
      <component :is="chartComponent" :data="chartData" v-if="chartData" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import OpenIssueChart from '@/components/charts/OpenIssueChart.vue'
import MonthBoxChart from '@/components/charts/MonthBoxChart.vue'
import LabelBarChart from '@/components/charts/LabelBarChart.vue'
import TermList from '@/components/charts/TermList.vue'

const props = defineProps<{
  title: string
  owner: string
  repo: string
  chartType: string
}>()

const chartData = ref<unknown>(null)
const loading = ref(true)
const error = ref<string | null>(null)

const chartComponent = computed(() => {
  switch (props.chartType) {
    case 'open-issues': return OpenIssueChart
    case 'label-frequency': return LabelBarChart
    case 'top-terms': return TermList
    default: return MonthBoxChart
  }
})

onMounted(async () => {
  try {
    const { data } = await axios.get(`/api/repos/${props.owner}/${props.repo}/charts/${props.chartType}`)
    chartData.value = data
  } catch (e: unknown) {
    error.value = 'Failed to load chart data'
  } finally {
    loading.value = false
  }
})
</script>
