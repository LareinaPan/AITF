<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { isAxiosError } from 'axios'

import {
  cancelPtRun,
  fetchPtRun,
  fetchPtRunErrors,
  fetchPtRunMetrics,
  isTerminalRunStatus,
  runStatusLabel,
  runStatusTagType,
  stopReasonLabel,
  type PtRunDetail,
  type PtRunErrorLog,
  type PtRunInterfaceSummary,
  type PtRunMetricPoint,
} from '@/api/pt-runs'
import { getApiErrorMessage } from '@/api/request'
import PtErrorLogPanel from '@/components/pt/PtErrorLogPanel.vue'
import PtMetricsChart from '@/components/pt/PtMetricsChart.vue'
import AsyncState from '@/components/common/AsyncState.vue'
import { formatBeijingTime } from '@/utils/datetime'

const POLL_INTERVAL_MS = 4000

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const loadError = ref<string | null>(null)
const cancelling = ref(false)
const run = ref<PtRunDetail | null>(null)
const metricPoints = ref<PtRunMetricPoint[]>([])
const errorLogs = ref<PtRunErrorLog[]>([])

const projectId = computed(() => route.params.id as string)
const runId = computed(() => route.params.runId as string)

const isRunning = computed(() => run.value?.status === 'running')

const summaryInterfaces = computed<PtRunInterfaceSummary[]>(
  () => run.value?.summary_json?.interfaces ?? [],
)

const samplerNames = computed<Record<string, string>>(() => {
  const mapping: Record<string, string> = {}
  for (const item of summaryInterfaces.value) {
    mapping[item.sampler_key] = item.name
  }
  return mapping
})

let pollTimer: ReturnType<typeof setInterval> | null = null

function sortMetricPoints(points: PtRunMetricPoint[]): PtRunMetricPoint[] {
  return [...points].sort(
    (left, right) =>
      new Date(left.recorded_at).getTime() - new Date(right.recorded_at).getTime(),
  )
}

function stopPolling(): void {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function startPolling(): void {
  stopPolling()
  pollTimer = setInterval(() => {
    void refreshRunningData()
  }, POLL_INTERVAL_MS)
}

async function loadMetrics(): Promise<void> {
  const response = await fetchPtRunMetrics(projectId.value, runId.value)
  metricPoints.value = sortMetricPoints(response.items)
}

async function loadErrors(): Promise<void> {
  const response = await fetchPtRunErrors(projectId.value, runId.value, { latest: 10 })
  errorLogs.value = response.items
}

async function loadRunDetail(): Promise<void> {
  run.value = await fetchPtRun(projectId.value, runId.value)
}

async function loadAllData(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    await loadRunDetail()
    await Promise.all([loadMetrics(), loadErrors()])
    if (isRunning.value) {
      startPolling()
    } else {
      stopPolling()
    }
  } catch (error) {
    loadError.value = getApiErrorMessage(error, '加载运行详情失败')
    run.value = null
    metricPoints.value = []
    errorLogs.value = []
    stopPolling()
  } finally {
    loading.value = false
  }
}

async function refreshRunningData(): Promise<void> {
  if (!isRunning.value) {
    return
  }
  try {
    await loadRunDetail()
    await Promise.all([loadMetrics(), loadErrors()])
    if (run.value && isTerminalRunStatus(run.value.status)) {
      stopPolling()
    }
  } catch {
    // Keep polling on transient failures during an active run.
  }
}

async function handleCancel(): Promise<void> {
  if (!run.value || !isRunning.value) {
    return
  }
  try {
    await ElMessageBox.confirm('确定取消当前压测吗？', '取消确认', {
      type: 'warning',
      confirmButtonText: '取消压测',
      cancelButtonText: '继续运行',
    })
  } catch {
    return
  }

  cancelling.value = true
  try {
    await cancelPtRun(projectId.value, runId.value)
    ElMessage.success('压测已取消')
    await loadAllData()
  } catch (error) {
    if (isAxiosError(error) && error.response?.status === 409) {
      ElMessage.warning('当前压测已结束，页面将自动刷新')
      await loadAllData()
      return
    }
    ElMessage.error(getApiErrorMessage(error, '取消压测失败'))
  } finally {
    cancelling.value = false
  }
}

function goBack(): void {
  router.push({ name: 'pt-project-runs', params: { id: projectId.value } })
}

onMounted(loadAllData)
onBeforeUnmount(stopPolling)

watch(runId, () => {
  void loadAllData()
})
</script>

<template>
  <AsyncState :loading="loading" :error="loadError" @retry="loadAllData">
    <div v-if="run" class="pt-run-detail-page">
      <el-page-header @back="goBack">
        <template #content>
          <div class="page-header-content">
            <span class="run-title">{{ run.scenario_name_snapshot }}</span>
            <el-tag :type="runStatusTagType(run.status)" size="small">
              {{ runStatusLabel(run.status) }}
            </el-tag>
          </div>
        </template>
      </el-page-header>

      <el-card shadow="never" class="detail-card">
        <div class="meta-row">
          <span>开始：{{ formatBeijingTime(run.started_at) }}</span>
          <span>结束：{{ run.ended_at ? formatBeijingTime(run.ended_at) : '—' }}</span>
          <span>停止原因：{{ stopReasonLabel(run.stop_reason) }}</span>
          <el-button
            v-if="isRunning"
            type="danger"
            plain
            :loading="cancelling"
            @click="handleCancel"
          >
            取消压测
          </el-button>
        </div>

        <el-alert
          v-if="run.error_message"
          :title="run.error_message"
          type="error"
          show-icon
          :closable="false"
          class="error-alert"
        />

        <section class="section-block">
          <h3 class="section-title">接口汇总指标</h3>
          <el-empty v-if="summaryInterfaces.length === 0" description="暂无汇总指标" />
          <el-table v-else :data="summaryInterfaces" stripe>
            <el-table-column prop="name" label="接口" min-width="160" />
            <el-table-column label="P99 RT (ms)" width="120">
              <template #default="{ row }">{{ row.rt_p99_ms }}</template>
            </el-table-column>
            <el-table-column label="P95 RT (ms)" width="120">
              <template #default="{ row }">{{ row.rt_p95_ms }}</template>
            </el-table-column>
            <el-table-column label="QPS" width="100">
              <template #default="{ row }">{{ row.qps }}</template>
            </el-table-column>
            <el-table-column label="错误率 (%)" width="110">
              <template #default="{ row }">{{ row.error_rate_percent }}</template>
            </el-table-column>
            <el-table-column label="总请求" width="100">
              <template #default="{ row }">{{ row.total_requests }}</template>
            </el-table-column>
            <el-table-column label="失败数" width="100">
              <template #default="{ row }">{{ row.failed_requests }}</template>
            </el-table-column>
          </el-table>
        </section>

        <section class="section-block">
          <h3 class="section-title">时序指标</h3>
          <p v-if="isRunning && metricPoints.length === 0" class="metrics-hint">
            压测指标每 3 秒刷新一次，请稍候…
          </p>
          <PtMetricsChart :points="metricPoints" :sampler-names="samplerNames" />
        </section>

        <section class="section-block">
          <PtErrorLogPanel
            :project-id="projectId"
            :run-id="runId"
            :errors="errorLogs"
          />
        </section>
      </el-card>
    </div>
  </AsyncState>
</template>

<style scoped>
.pt-run-detail-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header-content {
  display: flex;
  align-items: center;
  gap: 12px;
}

.run-title {
  font-size: 18px;
  font-weight: 600;
}

.detail-card {
  margin-top: 4px;
}

.meta-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 16px;
  color: #606266;
  font-size: 14px;
}

.error-alert {
  margin-bottom: 16px;
}

.section-block + .section-block {
  margin-top: 24px;
}

.section-title {
  margin: 0 0 12px;
  font-size: 16px;
  font-weight: 600;
}

.metrics-hint {
  margin: 0 0 12px;
  color: #909399;
  font-size: 13px;
}
</style>
