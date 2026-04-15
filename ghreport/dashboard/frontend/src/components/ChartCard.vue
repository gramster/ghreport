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
import { ref, computed, onMounted, watch } from 'vue'
import axios from 'axios'
import { useDateRangeStore } from '@/stores/dateRange'
import OpenIssueChart from '@/components/charts/OpenIssueChart.vue'
import MonthBoxChart from '@/components/charts/MonthBoxChart.vue'
import LabelBarChart from '@/components/charts/LabelBarChart.vue'
import TermList from '@/components/charts/TermList.vue'

const props = defineProps<{
  title: string
  owner?: string
  repo?: string
  chartType: string
  aggregate?: boolean
}>()

const dateRange = useDateRangeStore()

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const chartData = ref<any>(null)
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

async function fetchData() {
  loading.value = true
  error.value = null
  try {
    const url = props.aggregate
      ? `/api/aggregate/charts/${props.chartType}`
      : `/api/repos/${props.owner}/${props.repo}/charts/${props.chartType}`
    const { data } = await axios.get(url, { params: dateRange.params })
    chartData.value = data
  } catch (e: unknown) {
    error.value = 'Failed to load chart data'
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)
watch(() => [dateRange.since, dateRange.until], fetchData)
</script>
