<template>
  <div style="position: relative; height: 260px;">
    <Line :data="chartConfig" :options="options" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement,
  LineElement, Title, Tooltip, Legend,
} from 'chart.js'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend)

const props = defineProps<{
  data: {
    weeks: string[]
    [key: string]: (number | null)[] | string[]
  }
  yLabel?: string
  seriesConfig?: { key: string; label: string; color: string }[]
}>()

const defaultColors = [
  { bg: 'rgba(54, 162, 235, 0.5)', border: 'rgba(54, 162, 235, 1)' },
  { bg: 'rgba(255, 99, 132, 0.5)', border: 'rgba(255, 99, 132, 1)' },
  { bg: 'rgba(75, 192, 192, 0.5)', border: 'rgba(75, 192, 192, 1)' },
  { bg: 'rgba(255, 159, 64, 0.5)', border: 'rgba(255, 159, 64, 1)' },
]

const chartConfig = computed(() => {
  const weeks = props.data.weeks as string[]
  const seriesKeys = props.seriesConfig
    ? props.seriesConfig.map(s => s.key)
    : Object.keys(props.data).filter(k => k !== 'weeks')

  const datasets = seriesKeys.map((key, i) => {
    const cfg = props.seriesConfig?.find(s => s.key === key)
    const color = defaultColors[i % defaultColors.length]
    return {
      label: cfg?.label || key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
      data: props.data[key] as (number | null)[],
      borderColor: cfg?.color || color.border,
      backgroundColor: cfg?.color || color.bg,
      tension: 0.3,
      spanGaps: true,
      pointRadius: 1.5,
      borderWidth: 1.5,
      fill: false,
    }
  })

  return { labels: weeks, datasets }
})

const yMax = computed(() => {
  const seriesKeys = props.seriesConfig
    ? props.seriesConfig.map(s => s.key)
    : Object.keys(props.data).filter(k => k !== 'weeks')
  let max = 0
  for (const key of seriesKeys) {
    const vals = props.data[key] as (number | null)[]
    if (!vals) continue
    for (const v of vals) {
      if (v != null && v > max) max = v
    }
  }
  // Ensure the axis always has some headroom and never collapses to 0
  return Math.max(max * 1.15, 5)
})

const options = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: 'index' as const, intersect: false },
  plugins: {
    legend: {
      display: true,
      position: 'bottom' as const,
      labels: {
        boxWidth: 12,
        boxHeight: 12,
        padding: 12,
        font: { size: 11 },
        usePointStyle: true,
        pointStyle: 'rectRounded',
      },
    },
  },
  scales: {
    x: {
      ticks: { maxTicksLimit: 20, font: { size: 10 } },
    },
    y: {
      beginAtZero: true,
      suggestedMax: yMax.value,
      title: { display: true, text: props.yLabel || '' },
      ticks: { precision: 0 },
    },
  },
}))
</script>
