<template>
  <div style="position: relative; height: 260px;">
    <div class="chart-toolbar">
      <button class="toggle-btn" :class="{ active: showMA }" @click="showMA = !showMA" title="Toggle 4-week moving average">
        4w avg
      </button>
    </div>
    <Line :data="chartConfig" :options="options" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
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

const showMA = ref(false)
const MA_WINDOW = 4

function movingAverage(values: (number | null)[]): (number | null)[] {
  return values.map((_, i) => {
    const slice = values.slice(Math.max(0, i - MA_WINDOW + 1), i + 1).filter(v => v != null) as number[]
    if (slice.length === 0) return null
    return Math.round(slice.reduce((a, b) => a + b, 0) / slice.length * 10) / 10
  })
}

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
    const raw = props.data[key] as (number | null)[]
    const values = showMA.value ? movingAverage(raw) : raw
    return {
      label: cfg?.label || key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
      data: values,
      borderColor: cfg?.color || color.border,
      backgroundColor: cfg?.color || color.bg,
      tension: showMA.value ? 0.5 : 0.3,
      spanGaps: true,
      pointRadius: showMA.value ? 0 : 1.5,
      borderWidth: showMA.value ? 2 : 1.5,
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

<style scoped>
.chart-toolbar {
  position: absolute;
  top: 0;
  right: 0;
  z-index: 1;
}
.toggle-btn {
  font-size: 11px;
  padding: 2px 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
  background: #f5f5f5;
  color: #555;
  cursor: pointer;
  line-height: 1.6;
}
.toggle-btn:hover {
  background: #e8e8e8;
}
.toggle-btn.active {
  background: #4e89d4;
  border-color: #3a6fb5;
  color: #fff;
}
</style>
