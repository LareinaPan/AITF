<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { TableInstance } from 'element-plus'

import type { FcProject } from '@/api/fc-projects'
import { caseTypeLabel, fetchAllFcExperienceCases, type FcExperienceCase } from '@/api/fc-experience-cases'
import {
  batchStatusLabel,
  batchStatusProgress,
  batchStatusTagType,
  pollFcGenerationBatch,
  startFcGeneration,
  type FcGenerationBatch,
} from '@/api/fc-generation'
import {
  fetchFcRequirementDocs,
  parseStatusLabel,
  type FcRequirementDoc,
} from '@/api/fc-requirement-docs'
import { getApiErrorMessage } from '@/api/request'
import AsyncState from '@/components/common/AsyncState.vue'

const props = defineProps<{
  project: FcProject
}>()

const router = useRouter()

const loading = ref(false)
const loadError = ref<string | null>(null)
const generating = ref(false)
const docs = ref<FcRequirementDoc[]>([])
const experienceCases = ref<FcExperienceCase[]>([])
const selectedDocId = ref<string | null>(null)
const userFeedback = ref('')
const activeBatch = ref<FcGenerationBatch | null>(null)

const experienceTableRef = ref<TableInstance>()
const pollAbortController = ref<AbortController | null>(null)

const parsedDocs = computed(() => docs.value.filter((doc) => doc.parse_status === 'success'))

const canGenerate = computed(
  () => Boolean(selectedDocId.value) && !generating.value && parsedDocs.value.length > 0,
)

const progressPercent = computed(() => {
  if (!activeBatch.value) {
    return 0
  }
  return batchStatusProgress(activeBatch.value.status)
})

async function loadFormData(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    const [docList, caseList] = await Promise.all([
      fetchFcRequirementDocs(props.project.id),
      fetchAllFcExperienceCases(props.project.id),
    ])
    docs.value = docList
    experienceCases.value = caseList

    if (selectedDocId.value && !parsedDocs.value.some((doc) => doc.id === selectedDocId.value)) {
      selectedDocId.value = null
    }
    if (!selectedDocId.value && parsedDocs.value.length === 1) {
      selectedDocId.value = parsedDocs.value[0].id
    }
  } catch (error) {
    loadError.value = getApiErrorMessage(error, '加载生成配置失败')
  } finally {
    loading.value = false
  }
}

function getSelectedExperienceCaseIds(): string[] {
  const rows = experienceTableRef.value?.getSelectionRows() as FcExperienceCase[] | undefined
  return rows?.map((row) => row.id) ?? []
}

function stopPolling(): void {
  pollAbortController.value?.abort()
  pollAbortController.value = null
}

function goToReviewTab(batchId: string): void {
  router.push({
    name: 'fc-project-review',
    params: { id: props.project.id },
    query: { batchId },
  })
}

async function handleGenerate(): Promise<void> {
  if (!selectedDocId.value) {
    ElMessage.warning('请选择一份已解析成功的需求文档')
    return
  }

  generating.value = true
  activeBatch.value = null
  stopPolling()

  try {
    const result = await startFcGeneration(props.project.id, {
      requirement_doc_id: selectedDocId.value,
      experience_case_ids: getSelectedExperienceCaseIds(),
      user_feedback: userFeedback.value.trim() || null,
    })

    ElMessage.info('已提交生成任务，正在执行双 AI 流水线…')

    const controller = new AbortController()
    pollAbortController.value = controller

    const batch = await pollFcGenerationBatch(props.project.id, result.batch_id, {
      signal: controller.signal,
      onUpdate: (updated) => {
        activeBatch.value = updated
      },
    })
    activeBatch.value = batch

    if (batch.status === 'failed') {
      ElMessage.error(batch.error_message ?? 'AI 生成失败，请稍后重试')
      return
    }

    const coverageTip =
      batch.coverage_score != null ? `，覆盖度 ${batch.coverage_score.toFixed(1)}%` : ''
    ElMessage.success(`生成完成，共 ${batch.case_count} 条候选用例${coverageTip}`)
    goToReviewTab(batch.id)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      return
    }
    ElMessage.error(getApiErrorMessage(error, '发起 AI 生成失败'))
  } finally {
    generating.value = false
    stopPolling()
  }
}

function goDocsTab(): void {
  router.push({ name: 'fc-project-docs', params: { id: props.project.id } })
}

onMounted(loadFormData)
onUnmounted(stopPolling)
watch(
  () => props.project.id,
  () => {
    stopPolling()
    generating.value = false
    activeBatch.value = null
    void loadFormData()
  },
)
</script>

<template>
  <div class="fc-generate-tab">
    <AsyncState :loading="loading" :error="loadError" @retry="loadFormData">
      <div class="toolbar">
        <p class="hint">选择需求文档与可选经验用例，由双 AI 生成并审查功能测试用例</p>
      </div>

      <el-alert
        v-if="parsedDocs.length === 0"
        type="warning"
        show-icon
        :closable="false"
        class="empty-doc-alert"
      >
        <template #title>暂无可用的需求文档</template>
        <p class="alert-desc">请先在「需求文档」Tab 上传并成功解析 PRD 后再发起生成。</p>
        <el-button link type="primary" @click="goDocsTab">前往上传需求文档</el-button>
      </el-alert>

      <template v-else>
        <el-card shadow="never" class="section-card">
          <template #header>
            <span>1. 选择需求文档</span>
          </template>
          <el-radio-group v-model="selectedDocId" class="doc-radio-group" :disabled="generating">
            <el-radio
              v-for="doc in parsedDocs"
              :key="doc.id"
              :value="doc.id"
              class="doc-radio"
            >
              <span class="doc-name">{{ doc.filename }}</span>
              <el-tag size="small" type="success">{{ parseStatusLabel(doc.parse_status) }}</el-tag>
            </el-radio>
          </el-radio-group>
        </el-card>

        <el-card shadow="never" class="section-card">
          <template #header>
            <span>2. 引用经验用例（可选）</span>
          </template>
          <p class="section-hint">勾选后 AI 将参考其颗粒度与领域习惯，不会照搬内容</p>
          <el-table
            ref="experienceTableRef"
            :data="experienceCases"
            stripe
            empty-text="暂无经验用例，可跳过此步"
            max-height="280"
          >
            <el-table-column type="selection" width="48" :selectable="() => !generating" />
            <el-table-column prop="module" label="功能模块" min-width="120" show-overflow-tooltip />
            <el-table-column prop="title" label="用例标题" min-width="160" show-overflow-tooltip />
            <el-table-column label="类型" width="90" align="center">
              <template #default="{ row }">
                <el-tag size="small">{{ caseTypeLabel(row.case_type) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="priority" label="优先级" width="90" align="center" />
          </el-table>
        </el-card>

        <el-card shadow="never" class="section-card">
          <template #header>
            <span>3. 补充说明（可选）</span>
          </template>
          <el-input
            v-model="userFeedback"
            type="textarea"
            :rows="3"
            maxlength="2000"
            show-word-limit
            placeholder="例如：重点覆盖支付超时、并发下单等场景"
            :disabled="generating"
          />
        </el-card>

        <div class="actions">
          <el-button
            type="primary"
            size="large"
            :loading="generating"
            :disabled="!canGenerate"
            @click="handleGenerate"
          >
            {{ generating ? '生成中…' : '开始 AI 生成' }}
          </el-button>
        </div>
      </template>

      <el-card v-if="generating || activeBatch" shadow="never" class="progress-card">
        <template #header>
          <div class="progress-header">
            <span>生成进度</span>
            <el-tag v-if="activeBatch" :type="batchStatusTagType(activeBatch.status)" size="small">
              {{ batchStatusLabel(activeBatch.status) }}
            </el-tag>
          </div>
        </template>

        <el-progress
          :percentage="progressPercent"
          :status="activeBatch?.status === 'failed' ? 'exception' : undefined"
          :indeterminate="generating && !activeBatch"
        />

        <ul v-if="activeBatch" class="progress-meta">
          <li v-if="activeBatch.internal_retry_count > 0">
            内部优化轮次：{{ activeBatch.internal_retry_count }}
          </li>
          <li v-if="activeBatch.coverage_score != null">
            当前覆盖度：{{ activeBatch.coverage_score.toFixed(1) }}%
          </li>
          <li v-if="activeBatch.case_count > 0">候选用例：{{ activeBatch.case_count }} 条</li>
          <li v-if="activeBatch.error_message" class="error-text">
            {{ activeBatch.error_message }}
          </li>
        </ul>
        <p v-else class="progress-wait">任务已提交，等待后台执行…</p>
      </el-card>
    </AsyncState>
  </div>
</template>

<style scoped>
.fc-generate-tab {
  margin-top: 16px;
}

.toolbar {
  margin-bottom: 16px;
}

.hint {
  margin: 0;
  color: #909399;
  font-size: 13px;
}

.empty-doc-alert {
  margin-bottom: 16px;
}

.alert-desc {
  margin: 0 0 8px;
  color: #606266;
  font-size: 13px;
}

.section-card {
  margin-bottom: 16px;
}

.section-hint {
  margin: 0 0 12px;
  color: #909399;
  font-size: 13px;
}

.doc-radio-group {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
}

.doc-radio {
  height: auto;
  margin-right: 0;
  white-space: normal;
}

.doc-name {
  margin-right: 8px;
}

.actions {
  display: flex;
  justify-content: flex-start;
  margin-bottom: 16px;
}

.progress-card {
  margin-top: 8px;
}

.progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.progress-meta {
  margin: 16px 0 0;
  padding-left: 18px;
  color: #606266;
  font-size: 13px;
}

.progress-meta li + li {
  margin-top: 4px;
}

.error-text {
  color: #f56c6c;
}

.progress-wait {
  margin: 12px 0 0;
  color: #909399;
  font-size: 13px;
}
</style>
