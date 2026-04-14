<template>
  <Line :data="chartConfig" :options="options" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement,
  Title, Tooltip, Legend,
} from 'chart.js'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend)

const props = defineProps<{
  data: { points: { date: string; all_issues: number; bugs: number }[] }
}>()

const chartConfig = computed(() => ({
  labels: props.data.points.map(p => p.date),
  datasets: [
    {
      label: 'All Issues',
      data: props.data.points.map(p => p.all_issues),
      borderColor: '#0366d6',
      fill: false,
      tension: 0.1,
    },
    {
      label: 'Bugs',
      data: props.data.points.map(p => p.bugs),
      borderColor: '#cb2431',
      fill: false,
      tension: 0.1,
    },
  ],
}))

const options = {
  responsive: true,
  plugins: { legend: { position: 'top' as const } },
  scales: {
    x: { ticks: { maxTicksLimit: 12 } },
  },
}
</script>
