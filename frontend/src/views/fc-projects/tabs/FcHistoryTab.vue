<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import type { FcProject } from '@/api/fc-projects'
import {
  batchStatusLabel,
  batchStatusTagType,
  fetchFcGenerationBatches,
  type FcGenerationBatch,
  type FcReviewReport,
} from '@/api/fc-generation'
import { getApiErrorMessage } from '@/api/request'
import FcReviewReportPanel from '@/components/fc/FcReviewReportPanel.vue'
import AsyncState from '@/components/common/AsyncState.vue'
import { formatBeijingTime } from '@/utils/datetime'

const props = defineProps<{
  project: FcProject
}>()

const router = useRouter()

const loading = ref(false)
const loadError = ref<string | null>(null)
const batches = ref<FcGenerationBatch[]>([])
const expandedBatchIds = ref<string[]>([])

const sortedBatches = computed(() =>
  [...batches.value].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  ),
)

function getReviewReport(batch: FcGenerationBatch): FcReviewReport | null {
  const raw = batch.review_report_json
  return raw ? (raw as FcReviewReport) : null
}

async function loadHistory(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    batches.value = await fetchFcGenerationBatches(props.project.id)
  } catch (error) {
    loadError.value = getApiErrorMessage(error, '加载生成历史失败')
  } finally {
    loading.value = false
  }
}

function goReview(batchId: string): void {
  router.push({
    name: 'fc-project-review',
    params: { id: props.project.id },
    query: { batchId },
  })
}

onMounted(loadHistory)
watch(
  () => props.project.id,
  () => {
    expandedBatchIds.value = []
    void loadHistory()
  },
)
</script>

<template>
  <div class="fc-history-tab">
    <AsyncState :loading="loading" :error="loadError" @retry="loadHistory">
      <p class="hint">按时间倒序展示 AI 生成批次，可展开查看审查报告</p>

      <el-empty v-if="sortedBatches.length === 0" description="暂无生成历史" />

      <el-timeline v-else>
        <el-timeline-item
          v-for="batch in sortedBatches"
          :key="batch.id"
          :timestamp="formatBeijingTime(batch.created_at)"
          placement="top"
        >
          <el-card shadow="never" class="batch-card">
            <div class="batch-header">
              <div class="batch-meta">
                <el-tag :type="batchStatusTagType(batch.status)" size="small">
                  {{ batchStatusLabel(batch.status) }}
                </el-tag>
                <span class="batch-id">批次 {{ batch.id.slice(0, 8) }}</span>
                <span v-if="batch.coverage_score != null" class="coverage">
                  覆盖度 {{ batch.coverage_score.toFixed(1) }}%
                </span>
                <span class="case-count">{{ batch.case_count }} 条用例</span>
              </div>
              <div class="batch-actions">
                <el-button
                  v-if="batch.status === 'awaiting_review'"
                  link
                  type="primary"
                  @click="goReview(batch.id)"
                >
                  前往复查
                </el-button>
                <el-button
                  link
                  type="primary"
                  @click="
                    expandedBatchIds = expandedBatchIds.includes(batch.id)
                      ? expandedBatchIds.filter((id) => id !== batch.id)
                      : [...expandedBatchIds, batch.id]
                  "
                >
                  {{ expandedBatchIds.includes(batch.id) ? '收起报告' : '查看报告' }}
                </el-button>
              </div>
            </div>

            <div class="batch-extra">
              <span>触发人：{{ batch.triggered_by_username }}</span>
              <span v-if="batch.internal_retry_count > 0">
                内部优化 {{ batch.internal_retry_count }} 轮
              </span>
              <span v-if="batch.completed_at">
                完成于 {{ formatBeijingTime(batch.completed_at) }}
              </span>
              <span v-if="batch.user_feedback" class="feedback">
                用户反馈：{{ batch.user_feedback }}
              </span>
              <span v-if="batch.error_message" class="error-text">
                错误：{{ batch.error_message }}
              </span>
            </div>

            <div v-if="expandedBatchIds.includes(batch.id)" class="report-wrap">
              <FcReviewReportPanel
                :report="getReviewReport(batch)"
                :coverage-score="batch.coverage_score"
              />
            </div>
          </el-card>
        </el-timeline-item>
      </el-timeline>
    </AsyncState>
  </div>
</template>

<style scoped>
.fc-history-tab {
  margin-top: 16px;
}

.hint {
  margin: 0 0 16px;
  color: #909399;
  font-size: 13px;
}

.batch-card {
  margin-bottom: 4px;
}

.batch-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.batch-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.batch-id {
  color: #606266;
  font-size: 13px;
}

.coverage {
  color: #409eff;
  font-size: 13px;
  font-weight: 600;
}

.case-count {
  color: #909399;
  font-size: 13px;
}

.batch-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.batch-extra {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 10px;
  color: #909399;
  font-size: 12px;
}

.feedback {
  color: #606266;
}

.error-text {
  color: #f56c6c;
}

.report-wrap {
  margin-top: 12px;
}
</style>
