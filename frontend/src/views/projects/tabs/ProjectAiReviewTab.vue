<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import type { Project } from '@/api/projects'
import { getApiErrorMessage } from '@/api/request'
import {
  confirmTestCase,
  deleteTestCase,
  fetchTestCases,
  type TestCase,
  type TestCasePriority,
} from '@/api/testCases'
import AiDraftCasePreviewDrawer from '@/components/testcases/AiDraftCasePreviewDrawer.vue'
import { formatBeijingTime } from '@/utils/datetime'

const props = defineProps<{
  project: Project
}>()

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const confirmingId = ref<string | null>(null)
const rejectingId = ref<string | null>(null)
const draftCases = ref<TestCase[]>([])
const filterPriority = ref<TestCasePriority | ''>('')

const previewVisible = ref(false)
const previewCase = ref<TestCase | null>(null)

const filterApiId = computed(() => {
  const apiId = route.query.apiId
  return typeof apiId === 'string' ? apiId : ''
})

const filteredCases = computed(() =>
  draftCases.value.filter((item) => {
    if (filterPriority.value && item.priority !== filterPriority.value) {
      return false
    }
    if (filterApiId.value && item.api_endpoint_id !== filterApiId.value) {
      return false
    }
    return true
  }),
)

const priorityOptions: TestCasePriority[] = ['P0', 'P1', 'P2', 'P3']

function priorityTagType(priority: TestCasePriority): 'danger' | 'warning' | '' | 'info' {
  switch (priority) {
    case 'P0':
      return 'danger'
    case 'P1':
      return 'warning'
    case 'P2':
      return ''
    case 'P3':
      return 'info'
    default:
      return 'info'
  }
}

function methodTagType(method: string): 'success' | 'warning' | 'danger' | 'info' | '' {
  switch (method.toUpperCase()) {
    case 'GET':
      return 'success'
    case 'POST':
      return ''
    case 'PUT':
    case 'PATCH':
      return 'warning'
    case 'DELETE':
      return 'danger'
    default:
      return 'info'
  }
}

async function loadDraftCases(): Promise<void> {
  loading.value = true
  try {
    const allCases = await fetchTestCases(props.project.id)
    draftCases.value = allCases.filter((item) => item.status === 'draft')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '加载 AI 候选用例失败'))
  } finally {
    loading.value = false
  }
}

function openPreview(testCase: TestCase): void {
  previewCase.value = testCase
  previewVisible.value = true
}

function openEdit(testCase: TestCase): void {
  router.push({
    name: 'project-case-edit',
    params: { id: props.project.id, caseId: testCase.id },
  })
}

async function handleConfirm(testCase: TestCase): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定将「${testCase.name}」确认入库吗？确认后将变为正式用例。`,
      '确认入库',
      { type: 'info', confirmButtonText: '确认', cancelButtonText: '取消' },
    )
    confirmingId.value = testCase.id
    await confirmTestCase(props.project.id, testCase.id)
    ElMessage.success('用例已确认入库')

    if (previewCase.value?.id === testCase.id) {
      previewVisible.value = false
      previewCase.value = null
    }
    await loadDraftCases()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(getApiErrorMessage(error, '确认入库失败'))
    }
  } finally {
    confirmingId.value = null
  }
}

async function handleReject(testCase: TestCase): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定拒绝并删除「${testCase.name}」吗？此操作不可恢复。`,
      '拒绝候选',
      { type: 'warning', confirmButtonText: '拒绝', cancelButtonText: '取消' },
    )
    rejectingId.value = testCase.id
    await deleteTestCase(props.project.id, testCase.id)
    ElMessage.success('候选用例已拒绝')

    if (previewCase.value?.id === testCase.id) {
      previewVisible.value = false
      previewCase.value = null
    }
    await loadDraftCases()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(getApiErrorMessage(error, '拒绝候选用例失败'))
    }
  } finally {
    rejectingId.value = null
  }
}

function clearApiFilter(): void {
  router.replace({
    name: 'project-ai-review',
    params: { id: props.project.id },
  })
}

watch(
  () => [props.project.id, route.query.apiId] as const,
  () => {
    filterPriority.value = ''
    loadDraftCases()
  },
)

onMounted(loadDraftCases)
</script>

<template>
  <div class="ai-review-tab">
    <div class="review-toolbar">
      <div class="toolbar-left">
        <span class="toolbar-tip">审核 AI 生成的草稿用例，确认后入库，拒绝则删除。</span>
        <el-tag v-if="filterApiId" closable type="info" @close="clearApiFilter">
          仅显示当前接口候选用例
        </el-tag>
      </div>
      <el-select v-model="filterPriority" clearable placeholder="优先级" style="width: 120px">
        <el-option v-for="item in priorityOptions" :key="item" :label="item" :value="item" />
      </el-select>
    </div>

    <el-table
      v-loading="loading"
      :data="filteredCases"
      stripe
      empty-text="暂无 AI 候选用例，请先在接口管理中生成"
    >
      <el-table-column prop="name" label="用例名称" min-width="160" show-overflow-tooltip />
      <el-table-column label="方法" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="methodTagType(row.request_json.method)" size="small">
            {{ row.request_json.method }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="URL" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.request_json.url || '—' }}
        </template>
      </el-table-column>
      <el-table-column label="优先级" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="priorityTagType(row.priority)" size="small">
            {{ row.priority }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="生成时间" min-width="170">
        <template #default="{ row }">
          {{ formatBeijingTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openPreview(row)">预览</el-button>
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button
            link
            type="success"
            :loading="confirmingId === row.id"
            @click="handleConfirm(row)"
          >
            确认
          </el-button>
          <el-button
            link
            type="danger"
            :loading="rejectingId === row.id"
            @click="handleReject(row)"
          >
            拒绝
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <AiDraftCasePreviewDrawer v-model:visible="previewVisible" :test-case="previewCase" />
  </div>
</template>

<style scoped>
.ai-review-tab {
  margin-top: 8px;
}

.review-toolbar {
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
  flex-wrap: wrap;
}

.toolbar-tip {
  color: #909399;
  font-size: 13px;
}
</style>
