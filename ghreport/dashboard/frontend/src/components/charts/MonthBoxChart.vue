<template>
  <Bar :data="chartConfig" :options="options" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Bar } from 'vue-chartjs'
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement,
  Title, Tooltip, Legend,
} from 'chart.js'

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend)

const props = defineProps<{
  data: { months: Record<string, number[]> }
  yLabel?: string
}>()

const chartConfig = computed(() => {
  const months = Object.keys(props.data.months).sort()
  const medians = months.map(m => {
    const vals = props.data.months[m].sort((a, b) => a - b)
    const mid = Math.floor(vals.length / 2)
    return vals.length % 2 ? vals[mid] : (vals[mid - 1] + vals[mid]) / 2
  })

  return {
    labels: months,
    datasets: [
      {
        label: datasetLabel.value,
        data: medians,
        backgroundColor: 'rgba(54, 162, 235, 0.5)',
        borderColor: 'rgba(54, 162, 235, 1)',
        borderWidth: 1,
      },
    ],
  }
})

const yAxisLabel = computed(() => props.yLabel || 'Days')
const datasetLabel = computed(() => {
  const label = yAxisLabel.value
  return label === 'Days' ? 'Median (days)' : `Median ${label.toLowerCase()}`
})

const options = computed(() => ({
  responsive: true,
  plugins: { legend: { display: false } },
  scales: {
    x: { ticks: { maxTicksLimit: 12 } },
    y: {
      beginAtZero: true,
      title: { display: true, text: yAxisLabel.value },
    },
  },
}))
</script>
