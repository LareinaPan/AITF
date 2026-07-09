<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import type { EChartsOption } from 'echarts'

import {
  AGGREGATE_SAMPLER_KEY,
  samplerKeyLabel,
  type PtRunMetricPoint,
} from '@/api/pt-runs'
import { formatBeijingTime } from '@/utils/datetime'

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent])

type MetricType = 'qps' | 'avg_rt_ms' | 'error_rate_percent'

const props = defineProps<{
  points: PtRunMetricPoint[]
  samplerNames?: Record<string, string>
}>()

const selectedSamplerKey = ref<string>(AGGREGATE_SAMPLER_KEY)

const metricPanels: Array<{ key: MetricType; title: string; yAxisName: string }> = [
  { key: 'qps', title: 'QPS', yAxisName: 'QPS' },
  { key: 'avg_rt_ms', title: '平均 RT', yAxisName: 'RT (ms)' },
  { key: 'error_rate_percent', title: '错误率', yAxisName: '错误率 (%)' },
]

const samplerOptions = computed(() => {
  const keys = [...new Set(props.points.map((point) => point.sampler_key))]
  const ordered = keys.includes(AGGREGATE_SAMPLER_KEY)
    ? [AGGREGATE_SAMPLER_KEY, ...keys.filter((key) => key !== AGGREGATE_SAMPLER_KEY)]
    : keys
  return ordered.map((key) => ({
    value: key,
    label: samplerKeyLabel(key, props.samplerNames?.[key]),
  }))
})

const filteredPoints = computed(() =>
  [...props.points]
    .filter((point) => point.sampler_key === selectedSamplerKey.value)
    .sort(
      (left, right) =>
        new Date(left.recorded_at).getTime() - new Date(right.recorded_at).getTime(),
    ),
)

function buildChartOption(metricType: MetricType, yAxisName: string): EChartsOption {
  const labels = filteredPoints.value.map((point) => formatBeijingTime(point.recorded_at))
  const values = filteredPoints.value.map((point) => point[metricType])

  return {
    tooltip: {
      trigger: 'axis',
    },
    grid: {
      left: 48,
      right: 16,
      top: 24,
      bottom: 48,
    },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: {
        rotate: labels.length > 6 ? 35 : 0,
        fontSize: 11,
      },
    },
    yAxis: {
      type: 'value',
      name: yAxisName,
      nameTextStyle: {
        fontSize: 11,
      },
    },
    series: [
      {
        type: 'line',
        smooth: true,
        showSymbol: filteredPoints.value.length <= 24,
        data: values,
      },
    ],
  }
}

const chartOptions = computed(() =>
  metricPanels.map((panel) => ({
    ...panel,
    option: buildChartOption(panel.key, panel.yAxisName),
  })),
)

watch(
  samplerOptions,
  (options) => {
    if (!options.some((option) => option.value === selectedSamplerKey.value)) {
      selectedSamplerKey.value = options[0]?.value ?? AGGREGATE_SAMPLER_KEY
    }
  },
  { immediate: true },
)
</script>

<template>
  <div class="pt-metrics-chart">
    <div class="chart-toolbar">
      <span class="toolbar-label">接口</span>
      <el-select v-model="selectedSamplerKey" size="small" class="sampler-select">
        <el-option
          v-for="option in samplerOptions"
          :key="option.value"
          :label="option.label"
          :value="option.value"
        />
      </el-select>
    </div>

    <el-empty v-if="filteredPoints.length === 0" description="暂无时序指标数据" />
    <div v-else class="charts-grid">
      <div v-for="panel in chartOptions" :key="panel.key" class="chart-panel">
        <h4 class="chart-title">{{ panel.title }}</h4>
        <VChart class="chart-canvas" :option="panel.option" autoresize />
      </div>
    </div>
  </div>
</template>

<style scoped>
.pt-metrics-chart {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chart-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toolbar-label {
  color: #606266;
  font-size: 14px;
}

.sampler-select {
  width: 220px;
}

.charts-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.chart-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  padding: 12px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fafafa;
}

.chart-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.chart-canvas {
  width: 100%;
  height: 260px;
}

@media (max-width: 1200px) {
  .charts-grid {
    grid-template-columns: 1fr;
  }

  .chart-canvas {
    height: 300px;
  }
}
</style>
