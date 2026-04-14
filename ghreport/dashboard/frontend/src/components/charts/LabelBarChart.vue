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
  data: { labels: { name: string; count: number }[] }
}>()

const chartConfig = computed(() => {
  const top = props.data.labels.slice(0, 20)
  return {
    labels: top.map(l => l.name),
    datasets: [
      {
        label: 'Issues',
        data: top.map(l => l.count),
        backgroundColor: 'rgba(75, 192, 192, 0.5)',
        borderColor: 'rgba(75, 192, 192, 1)',
        borderWidth: 1,
      },
    ],
  }
})

const options = {
  responsive: true,
  indexAxis: 'y' as const,
  plugins: { legend: { display: false } },
}
</script>
