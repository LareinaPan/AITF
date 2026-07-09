<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules, TableInstance } from 'element-plus'

import type { FcProject } from '@/api/fc-projects'
import {
  FC_CASE_TYPE_OPTIONS,
  FC_PRIORITY_OPTIONS,
  caseTypeLabel,
  type FcCaseType,
  type FcPriority,
} from '@/api/fc-experience-cases'
import {
  batchStatusLabel,
  batchStatusTagType,
  confirmBatchCases,
  fetchBatchDraftCases,
  fetchFcGenerationBatch,
  fetchFcGenerationBatches,
  isTerminalBatchStatus,
  pollFcGenerationBatch,
  rejectBatchAndRegenerate,
  type FcGenerationBatch,
  type FcReviewReport,
} from '@/api/fc-generation'
import { deleteFcTestCase, updateFcTestCase, type FcTestCase } from '@/api/fc-test-cases'
import { getApiErrorMessage } from '@/api/request'
import FcReviewReportPanel from '@/components/fc/FcReviewReportPanel.vue'
import AsyncState from '@/components/common/AsyncState.vue'

const props = defineProps<{
  project: FcProject
}>()

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const loadError = ref<string | null>(null)
const actionLoading = ref(false)
const polling = ref(false)
const batches = ref<FcGenerationBatch[]>([])
const selectedBatchId = ref<string | null>(null)
const activeBatch = ref<FcGenerationBatch | null>(null)
const draftCases = ref<FcTestCase[]>([])

const rejectDialogVisible = ref(false)
const rejectFeedback = ref('')

const editDialogVisible = ref(false)
const editingCase = ref<FcTestCase | null>(null)
const editFormRef = ref<FormInstance>()
const editForm = reactive({
  case_no: '',
  module: '',
  title: '',
  preconditions: '',
  steps: '',
  expected_result: '',
  priority: 'P2' as FcPriority,
  case_type: 'positive' as FcCaseType,
})

const casesTableRef = ref<TableInstance>()
const pollAbortController = ref<AbortController | null>(null)

const editRules: FormRules = {
  module: [{ required: true, message: '请输入功能模块', trigger: 'blur' }],
  title: [{ required: true, message: '请输入用例标题', trigger: 'blur' }],
  steps: [{ required: true, message: '请输入测试步骤', trigger: 'blur' }],
  expected_result: [{ required: true, message: '请输入预期结果', trigger: 'blur' }],
}

const reviewableBatches = computed(() =>
  batches.value.filter((batch) =>
    ['awaiting_review', 'completed', 'pending', 'generating', 'reviewing'].includes(batch.status),
  ),
)

const reviewReport = computed<FcReviewReport | null>(() => {
  const raw = activeBatch.value?.review_report_json
  return raw ? (raw as FcReviewReport) : null
})

const canReviewActions = computed(() => activeBatch.value?.status === 'awaiting_review')

function stopPolling(): void {
  pollAbortController.value?.abort()
  pollAbortController.value = null
  polling.value = false
}

async function loadDraftCases(batchId: string): Promise<void> {
  if (!activeBatch.value || !isTerminalBatchStatus(activeBatch.value.status)) {
    draftCases.value = []
    return
  }
  if (activeBatch.value.status === 'failed') {
    draftCases.value = []
    return
  }
  draftCases.value = await fetchBatchDraftCases(props.project.id, batchId)
}

async function loadBatchDetail(batchId: string): Promise<void> {
  activeBatch.value = await fetchFcGenerationBatch(props.project.id, batchId)
  if (!isTerminalBatchStatus(activeBatch.value.status)) {
    await startPolling(batchId)
    return
  }
  await loadDraftCases(batchId)
}

async function startPolling(batchId: string): Promise<void> {
  stopPolling()
  polling.value = true
  const controller = new AbortController()
  pollAbortController.value = controller

  try {
    const batch = await pollFcGenerationBatch(props.project.id, batchId, {
      signal: controller.signal,
      onUpdate: (updated) => {
        activeBatch.value = updated
      },
    })
    activeBatch.value = batch
    await loadDraftCases(batchId)
    if (batch.status === 'awaiting_review') {
      ElMessage.success('新批次生成完成，可进行复查')
    }
  } catch (error) {
    if (!(error instanceof DOMException && error.name === 'AbortError')) {
      ElMessage.error(getApiErrorMessage(error, '轮询批次状态失败'))
    }
  } finally {
    polling.value = false
    stopPolling()
  }
}

async function loadReviewData(preferredBatchId?: string | null): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    batches.value = await fetchFcGenerationBatches(props.project.id)
    const queryBatchId = typeof preferredBatchId === 'string' ? preferredBatchId : null
    const fallbackBatchId = reviewableBatches.value[0]?.id ?? null
    const nextBatchId =
      queryBatchId && batches.value.some((batch) => batch.id === queryBatchId)
        ? queryBatchId
        : selectedBatchId.value && batches.value.some((batch) => batch.id === selectedBatchId.value)
          ? selectedBatchId.value
          : fallbackBatchId

    selectedBatchId.value = nextBatchId
    if (nextBatchId) {
      await loadBatchDetail(nextBatchId)
    } else {
      activeBatch.value = null
      draftCases.value = []
    }
  } catch (error) {
    loadError.value = getApiErrorMessage(error, '加载复查数据失败')
  } finally {
    loading.value = false
  }
}

function getSelectedCaseIds(): string[] {
  const rows = casesTableRef.value?.getSelectionRows() as FcTestCase[] | undefined
  return rows?.map((row) => row.id) ?? []
}

async function handleBatchChange(batchId: string | number | boolean | object | null | undefined): Promise<void> {
  if (typeof batchId !== 'string' || !batchId) {
    return
  }
  stopPolling()
  selectedBatchId.value = batchId
  router.replace({
    name: 'fc-project-review',
    params: { id: props.project.id },
    query: { batchId },
  })
  loading.value = true
  try {
    await loadBatchDetail(batchId)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '加载批次详情失败'))
  } finally {
    loading.value = false
  }
}

async function handleConfirmSelected(): Promise<void> {
  if (!selectedBatchId.value || !canReviewActions.value) {
    return
  }
  const caseIds = getSelectedCaseIds()
  if (caseIds.length === 0) {
    ElMessage.warning('请先勾选要入库的用例')
    return
  }

  actionLoading.value = true
  try {
    const result = await confirmBatchCases(props.project.id, selectedBatchId.value, caseIds)
    ElMessage.success(`已确认入库 ${result.confirmed_count} 条用例`)
    await loadReviewData(selectedBatchId.value)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '确认入库失败'))
  } finally {
    actionLoading.value = false
  }
}

async function handleConfirmAll(): Promise<void> {
  if (!selectedBatchId.value || !canReviewActions.value) {
    return
  }

  try {
    await ElMessageBox.confirm('确认将本批次全部候选用例入库？', '确认入库', {
      type: 'warning',
      confirmButtonText: '确认',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }

  actionLoading.value = true
  try {
    const result = await confirmBatchCases(props.project.id, selectedBatchId.value, [])
    ElMessage.success(`已确认入库 ${result.confirmed_count} 条用例`)
    await loadReviewData(selectedBatchId.value)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '确认入库失败'))
  } finally {
    actionLoading.value = false
  }
}

function openRejectDialog(): void {
  rejectFeedback.value = ''
  rejectDialogVisible.value = true
}

async function handleRejectSubmit(): Promise<void> {
  if (!selectedBatchId.value || !canReviewActions.value) {
    return
  }
  const feedback = rejectFeedback.value.trim()
  if (!feedback) {
    ElMessage.warning('请填写修改意见')
    return
  }

  actionLoading.value = true
  try {
    const result = await rejectBatchAndRegenerate(
      props.project.id,
      selectedBatchId.value,
      feedback,
    )
    rejectDialogVisible.value = false
    ElMessage.info('已提交驳回并重新生成，请等待新批次完成')
    selectedBatchId.value = result.batch_id
    router.replace({
      name: 'fc-project-review',
      params: { id: props.project.id },
      query: { batchId: result.batch_id },
    })
    await loadReviewData(result.batch_id)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '驳回并重新生成失败'))
  } finally {
    actionLoading.value = false
  }
}

function openEditDialog(item: FcTestCase): void {
  editingCase.value = item
  editForm.case_no = item.case_no
  editForm.module = item.module
  editForm.title = item.title
  editForm.preconditions = item.preconditions ?? ''
  editForm.steps = item.steps
  editForm.expected_result = item.expected_result
  editForm.priority = item.priority
  editForm.case_type = item.case_type
  editDialogVisible.value = true
}

async function handleEditSubmit(): Promise<void> {
  if (!editFormRef.value || !editingCase.value) {
    return
  }
  const valid = await editFormRef.value.validate().catch(() => false)
  if (!valid) {
    return
  }

  actionLoading.value = true
  try {
    await updateFcTestCase(props.project.id, editingCase.value.id, {
      case_no: editForm.case_no.trim(),
      module: editForm.module.trim(),
      title: editForm.title.trim(),
      preconditions: editForm.preconditions.trim() || null,
      steps: editForm.steps.trim(),
      expected_result: editForm.expected_result.trim(),
      priority: editForm.priority,
      case_type: editForm.case_type,
    })
    editDialogVisible.value = false
    ElMessage.success('用例已更新')
    if (selectedBatchId.value) {
      await loadDraftCases(selectedBatchId.value)
    }
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '更新用例失败'))
  } finally {
    actionLoading.value = false
  }
}

async function handleDeleteCase(item: FcTestCase): Promise<void> {
  try {
    await ElMessageBox.confirm(`确定删除候选用例「${item.title}」吗？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    actionLoading.value = true
    await deleteFcTestCase(props.project.id, item.id)
    ElMessage.success('候选用例已删除')
    if (selectedBatchId.value) {
      await loadDraftCases(selectedBatchId.value)
    }
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(getApiErrorMessage(error, '删除用例失败'))
    }
  } finally {
    actionLoading.value = false
  }
}

function goGenerateTab(): void {
  router.push({ name: 'fc-project-generate', params: { id: props.project.id } })
}

onMounted(() => {
  const queryBatchId = typeof route.query.batchId === 'string' ? route.query.batchId : null
  void loadReviewData(queryBatchId)
})

onUnmounted(stopPolling)

watch(
  () => props.project.id,
  () => {
    stopPolling()
    void loadReviewData()
  },
)

watch(
  () => route.query.batchId,
  (batchId) => {
    if (typeof batchId === 'string' && batchId !== selectedBatchId.value) {
      void handleBatchChange(batchId)
    }
  },
)
</script>

<template>
  <div class="fc-review-tab">
    <AsyncState :loading="loading" :error="loadError" @retry="() => loadReviewData(selectedBatchId)">
      <div class="toolbar">
        <div class="toolbar-left">
          <span class="label">复查批次</span>
          <el-select
            :model-value="selectedBatchId"
            placeholder="选择生成批次"
            style="width: 320px"
            :disabled="polling"
            @update:model-value="handleBatchChange"
          >
            <el-option
              v-for="batch in reviewableBatches"
              :key="batch.id"
              :label="`${batchStatusLabel(batch.status)} · ${batch.case_count} 条 · ${batch.id.slice(0, 8)}`"
              :value="batch.id"
            />
          </el-select>
          <el-tag v-if="activeBatch" :type="batchStatusTagType(activeBatch.status)" size="small">
            {{ batchStatusLabel(activeBatch.status) }}
          </el-tag>
        </div>
        <div v-if="canReviewActions" class="toolbar-actions">
          <el-button :loading="actionLoading" @click="handleConfirmSelected">确认选中入库</el-button>
          <el-button type="primary" :loading="actionLoading" @click="handleConfirmAll">
            全部确认入库
          </el-button>
          <el-button type="danger" plain :loading="actionLoading" @click="openRejectDialog">
            驳回并重新生成
          </el-button>
        </div>
      </div>

      <el-alert
        v-if="!selectedBatchId"
        type="info"
        show-icon
        :closable="false"
        title="暂无可复查的生成批次"
        description="请先在「AI 生成」Tab 发起生成任务。"
        class="empty-alert"
      >
        <el-button link type="primary" @click="goGenerateTab">前往 AI 生成</el-button>
      </el-alert>

      <template v-else-if="activeBatch">
        <el-alert
          v-if="polling"
          type="warning"
          show-icon
          :closable="false"
          title="新批次生成中"
          description="系统正在执行双 AI 流水线，完成后将自动刷新候选用例。"
          class="progress-alert"
        />

        <FcReviewReportPanel
          :report="reviewReport"
          :coverage-score="activeBatch.coverage_score"
        />

        <el-card shadow="never">
          <template #header>
            <span>候选用例（{{ draftCases.length }}）</span>
          </template>

          <el-table
            ref="casesTableRef"
            v-loading="polling"
            :data="draftCases"
            stripe
            empty-text="暂无 draft 候选用例"
          >
            <el-table-column type="selection" width="48" :selectable="() => canReviewActions" />
            <el-table-column prop="case_no" label="编号" width="100" />
            <el-table-column prop="module" label="功能模块" min-width="120" show-overflow-tooltip />
            <el-table-column prop="title" label="用例标题" min-width="160" show-overflow-tooltip />
            <el-table-column label="类型" width="90" align="center">
              <template #default="{ row }">
                <el-tag size="small">{{ caseTypeLabel(row.case_type) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="priority" label="优先级" width="90" align="center" />
            <el-table-column label="操作" width="140" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openEditDialog(row)">编辑</el-button>
                <el-button
                  link
                  type="danger"
                  :disabled="!canReviewActions"
                  @click="handleDeleteCase(row)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </template>
    </AsyncState>

    <el-dialog v-model="rejectDialogVisible" title="驳回并重新生成" width="520px" destroy-on-close>
      <p class="dialog-hint">请描述需要补充或修改的测试场景，AI 将据此重新生成候选用例。</p>
      <el-input
        v-model="rejectFeedback"
        type="textarea"
        :rows="5"
        maxlength="2000"
        show-word-limit
        placeholder="例如：请补充支付超时、并发下单、忘记密码等场景"
      />
      <template #footer>
        <el-button @click="rejectDialogVisible = false">取消</el-button>
        <el-button type="danger" :loading="actionLoading" @click="handleRejectSubmit">
          提交驳回
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="editDialogVisible"
      title="编辑候选用例"
      width="640px"
      destroy-on-close
    >
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="96px">
        <el-form-item label="用例编号">
          <el-input v-model="editForm.case_no" maxlength="64" />
        </el-form-item>
        <el-form-item label="功能模块" prop="module">
          <el-input v-model="editForm.module" maxlength="128" />
        </el-form-item>
        <el-form-item label="用例标题" prop="title">
          <el-input v-model="editForm.title" maxlength="256" />
        </el-form-item>
        <el-form-item label="前置条件">
          <el-input v-model="editForm.preconditions" type="textarea" :rows="2" maxlength="4000" />
        </el-form-item>
        <el-form-item label="测试步骤" prop="steps">
          <el-input v-model="editForm.steps" type="textarea" :rows="4" maxlength="8000" />
        </el-form-item>
        <el-form-item label="预期结果" prop="expected_result">
          <el-input v-model="editForm.expected_result" type="textarea" :rows="3" maxlength="8000" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="editForm.priority" style="width: 120px">
            <el-option v-for="item in FC_PRIORITY_OPTIONS" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="用例类型">
          <el-select v-model="editForm.case_type" style="width: 160px">
            <el-option
              v-for="item in FC_CASE_TYPE_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="actionLoading" @click="handleEditSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.fc-review-tab {
  margin-top: 16px;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.label {
  color: #606266;
  font-size: 14px;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.empty-alert,
.progress-alert {
  margin-bottom: 16px;
}

.dialog-hint {
  margin: 0 0 12px;
  color: #909399;
  font-size: 13px;
}
</style>
