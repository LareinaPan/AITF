<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { TableInstance } from 'element-plus'

import type { FcProject } from '@/api/fc-projects'
import {
  FC_CASE_TYPE_OPTIONS,
  caseTypeLabel,
  type FcCaseType,
} from '@/api/fc-experience-cases'
import {
  fetchFcTestCases,
  fetchFcTestCaseFilterOptions,
  batchDeleteFcTestCases,
  type FcTestCase,
} from '@/api/fc-test-cases'
import { exportFcCasesExcel, exportFcCasesXmind } from '@/api/fc-export'
import { getApiErrorMessage } from '@/api/request'
import AsyncState from '@/components/common/AsyncState.vue'
import { formatBeijingTime } from '@/utils/datetime'

const props = defineProps<{
  project: FcProject
}>()

const loading = ref(false)
const loadError = ref<string | null>(null)
const exporting = ref(false)
const deleting = ref(false)
const cases = ref<FcTestCase[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const casesTableRef = ref<TableInstance>()
const moduleFilter = ref('')
const caseTypeFilter = ref<FcCaseType | ''>('')
const batchFilter = ref('')
const moduleOptions = ref<string[]>([])
const batchOptions = ref<Array<{ value: string; label: string }>>([])

const BATCH_NONE = '__none__'

function buildListParams() {
  const params: {
    status: 'active'
    page: number
    page_size: number
    module?: string
    case_type?: FcCaseType
    generation_batch_id?: string
    no_batch?: boolean
  } = {
    status: 'active',
    page: page.value,
    page_size: pageSize.value,
  }

  if (moduleFilter.value) {
    params.module = moduleFilter.value
  }
  if (caseTypeFilter.value) {
    params.case_type = caseTypeFilter.value
  }
  if (batchFilter.value) {
    if (batchFilter.value === BATCH_NONE) {
      params.no_batch = true
    } else {
      params.generation_batch_id = batchFilter.value
    }
  }
  return params
}

function buildBatchOptions(
  batchIds: string[],
  hasNoBatch: boolean,
): Array<{ value: string; label: string }> {
  const options = batchIds.map((id) => ({
    value: id,
    label: formatBatchNo(id),
  }))
  if (hasNoBatch) {
    options.push({ value: BATCH_NONE, label: '无批次' })
  }
  return options
}

async function loadFilterOptions(): Promise<void> {
  try {
    const options = await fetchFcTestCaseFilterOptions(props.project.id, 'active')
    moduleOptions.value = options.modules
    batchOptions.value = buildBatchOptions(options.generation_batch_ids, options.has_no_batch)
  } catch {
    moduleOptions.value = []
    batchOptions.value = []
  }
}

const detailVisible = ref(false)
const selectedCase = ref<FcTestCase | null>(null)

function formatBatchNo(batchId: string | null): string {
  if (!batchId) {
    return '—'
  }
  return batchId.slice(0, 8)
}

async function loadCases(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    const result = await fetchFcTestCases(props.project.id, buildListParams())
    cases.value = result.items
    total.value = result.total
    if (total.value > 0 && cases.value.length === 0 && page.value > 1) {
      page.value -= 1
      await loadCases()
      return
    }
  } catch (error) {
    loadError.value = getApiErrorMessage(error, '加载用例库失败')
  } finally {
    loading.value = false
  }
}

async function loadPageData(): Promise<void> {
  await Promise.all([loadFilterOptions(), loadCases()])
}

function handlePageChange(nextPage: number): void {
  page.value = nextPage
  void loadCases()
}

function handleSizeChange(nextSize: number): void {
  pageSize.value = nextSize
  page.value = 1
  void loadCases()
}

function handleFilterChange(): void {
  page.value = 1
  void loadCases()
}

function openDetail(item: FcTestCase): void {
  selectedCase.value = item
  detailVisible.value = true
}

function buildExportFilters() {
  const filters: {
    status: 'active'
    module?: string
    case_type?: FcCaseType
    generation_batch_id?: string
    no_batch?: boolean
  } = { status: 'active' }

  if (moduleFilter.value) {
    filters.module = moduleFilter.value
  }
  if (caseTypeFilter.value) {
    filters.case_type = caseTypeFilter.value
  }
  if (batchFilter.value) {
    if (batchFilter.value === BATCH_NONE) {
      filters.no_batch = true
    } else {
      filters.generation_batch_id = batchFilter.value
    }
  }
  return filters
}

async function handleExport(format: 'excel' | 'xmind'): Promise<void> {
  if (total.value === 0) {
    ElMessage.warning('当前筛选条件下没有可导出的用例')
    return
  }

  exporting.value = true
  try {
    const filters = buildExportFilters()
    if (format === 'excel') {
      await exportFcCasesExcel(props.project.id, filters)
      ElMessage.success('Excel 导出成功')
    } else {
      await exportFcCasesXmind(props.project.id, filters)
      ElMessage.success('XMind 导出成功')
    }
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '导出失败'))
  } finally {
    exporting.value = false
  }
}

async function handleBatchDelete(): Promise<void> {
  const selected = casesTableRef.value?.getSelectionRows() as FcTestCase[] | undefined
  if (!selected?.length) {
    ElMessage.warning('请先选择要删除的用例')
    return
  }

  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${selected.length} 条用例吗？删除后不可恢复。`,
      '批量删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }

  deleting.value = true
  try {
    const deletedCount = await batchDeleteFcTestCases(
      props.project.id,
      selected.map((item) => item.id),
    )
    ElMessage.success(`已删除 ${deletedCount} 条用例`)
    casesTableRef.value?.clearSelection()
    await loadPageData()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '批量删除失败'))
  } finally {
    deleting.value = false
  }
}

onMounted(loadPageData)
watch(
  () => props.project.id,
  () => {
    moduleFilter.value = ''
    caseTypeFilter.value = ''
    batchFilter.value = ''
    page.value = 1
    void loadPageData()
  },
)
</script>

<template>
  <div class="fc-cases-tab">
    <AsyncState :loading="loading" :error="loadError" @retry="loadPageData">
      <div class="toolbar">
        <p class="hint">仅展示已确认入库的正式用例（status=active）</p>
        <div class="filters">
          <el-button
            type="danger"
            plain
            :loading="deleting"
            :disabled="total === 0"
            @click="handleBatchDelete"
          >
            批量删除
          </el-button>
          <el-dropdown trigger="click" @command="handleExport">
            <el-button type="primary" :loading="exporting">
              导出
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="excel">导出 Excel (.xlsx)</el-dropdown-item>
                <el-dropdown-item command="xmind">导出 XMind (.xmind)</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-select
            v-model="moduleFilter"
            clearable
            placeholder="功能模块"
            style="width: 160px"
            @change="handleFilterChange"
          >
            <el-option v-for="item in moduleOptions" :key="item" :label="item" :value="item" />
          </el-select>
          <el-select
            v-model="caseTypeFilter"
            clearable
            placeholder="用例类型"
            style="width: 140px"
            @change="handleFilterChange"
          >
            <el-option
              v-for="item in FC_CASE_TYPE_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
          <el-select
            v-model="batchFilter"
            clearable
            filterable
            placeholder="批次号"
            style="width: 140px"
            @change="handleFilterChange"
          >
            <el-option
              v-for="item in batchOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            >
              <span class="batch-option-label">{{ item.label }}</span>
              <span v-if="item.value !== BATCH_NONE" class="batch-option-id">
                {{ item.value }}
              </span>
            </el-option>
          </el-select>
        </div>
      </div>

      <el-table
        ref="casesTableRef"
        v-loading="loading"
        :data="cases"
        stripe
        empty-text="暂无正式用例，请在「用例复查」中确认入库"
      >
        <el-table-column type="selection" width="48" />
        <el-table-column prop="case_no" label="编号" width="100" />
        <el-table-column prop="module" label="功能模块" min-width="120" show-overflow-tooltip />
        <el-table-column prop="title" label="用例标题" min-width="180" show-overflow-tooltip />
        <el-table-column label="类型" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small">{{ caseTypeLabel(row.case_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="90" align="center" />
        <el-table-column label="批次号" width="100" align="center">
          <template #default="{ row }">
            <el-tooltip v-if="row.generation_batch_id" :content="row.generation_batch_id" placement="top">
              <span class="batch-no">{{ formatBatchNo(row.generation_batch_id) }}</span>
            </el-tooltip>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="入库时间" min-width="170">
          <template #default="{ row }">
            {{ formatBeijingTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="total > 0" class="pagination-bar">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </AsyncState>

    <el-drawer v-model="detailVisible" title="用例详情" size="480px" destroy-on-close>
      <template v-if="selectedCase">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="编号">{{ selectedCase.case_no }}</el-descriptions-item>
          <el-descriptions-item label="功能模块">{{ selectedCase.module }}</el-descriptions-item>
          <el-descriptions-item label="用例标题">{{ selectedCase.title }}</el-descriptions-item>
          <el-descriptions-item label="类型">
            {{ caseTypeLabel(selectedCase.case_type) }}
          </el-descriptions-item>
          <el-descriptions-item label="优先级">{{ selectedCase.priority }}</el-descriptions-item>
          <el-descriptions-item label="批次号">
            {{ selectedCase.generation_batch_id || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="前置条件">
            {{ selectedCase.preconditions || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="测试步骤">
            <pre class="detail-text">{{ selectedCase.steps }}</pre>
          </el-descriptions-item>
          <el-descriptions-item label="预期结果">
            <pre class="detail-text">{{ selectedCase.expected_result }}</pre>
          </el-descriptions-item>
        </el-descriptions>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.fc-cases-tab {
  margin-top: 16px;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.hint {
  margin: 0;
  color: #909399;
  font-size: 13px;
}

.filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.batch-no {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  color: #606266;
  cursor: default;
}

.batch-option-label {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  margin-right: 8px;
}

.batch-option-id {
  color: #909399;
  font-size: 12px;
}

.detail-text {
  margin: 0;
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.5;
}
</style>
