<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadInstance, UploadRawFile } from 'element-plus'

import {
  deleteApiEndpoint,
  fetchApiEndpoints,
  methodTagType,
  uploadOpenApi,
  type AIGenerateResult,
  type ApiEndpoint,
} from '@/api/apiEndpoints'
import type { Project } from '@/api/projects'
import { getApiErrorMessage } from '@/api/request'
import { formatBeijingTime } from '@/utils/datetime'
import AiGenerateDialog from '@/components/apis/AiGenerateDialog.vue'
import ApiEndpointDetailDrawer from '@/components/apis/ApiEndpointDetailDrawer.vue'
import AsyncState from '@/components/common/AsyncState.vue'

const props = defineProps<{
  project: Project
}>()

const router = useRouter()

const loading = ref(false)
const loadError = ref<string | null>(null)
const uploading = ref(false)
const deletingId = ref<string | null>(null)
const endpoints = ref<ApiEndpoint[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

const uploadRef = ref<UploadInstance>()
const detailDrawerVisible = ref(false)
const selectedEndpointId = ref<string | null>(null)
const generateDialogVisible = ref(false)
const generateEndpoint = ref<ApiEndpoint | null>(null)

async function loadEndpoints(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    const result = await fetchApiEndpoints(props.project.id, page.value, pageSize.value)
    endpoints.value = result.items
    total.value = result.total
  } catch (error) {
    loadError.value = getApiErrorMessage(error, '加载接口列表失败')
  } finally {
    loading.value = false
  }
}

async function handleUpload(rawFile: UploadRawFile): Promise<boolean> {
  uploading.value = true
  try {
    const result = await uploadOpenApi(props.project.id, rawFile)
    ElMessage.success(
      `上传成功：新增 ${result.created} 条，更新 ${result.updated} 条`,
    )
    page.value = 1
    await loadEndpoints()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '上传 OpenAPI 文件失败'))
  } finally {
    uploading.value = false
    uploadRef.value?.clearFiles()
  }

  return false
}

function openDetail(endpoint: ApiEndpoint): void {
  selectedEndpointId.value = endpoint.id
  detailDrawerVisible.value = true
}

function openCreatePage(apiId: string): void {
  router.push({
    name: 'project-case-create',
    params: { id: props.project.id },
    query: { apiId },
  })
}

function openGenerateDialog(endpoint: ApiEndpoint): void {
  generateEndpoint.value = endpoint
  generateDialogVisible.value = true
}

function handleGenerated(result: AIGenerateResult): void {
  if (result.cases.length === 0) {
    return
  }
  router.push({
    name: 'project-ai-review',
    params: { id: props.project.id },
    query: generateEndpoint.value ? { apiId: generateEndpoint.value.id } : undefined,
  })
}

async function handleDelete(endpoint: ApiEndpoint): Promise<void> {
  const label = endpoint.summary
    ? `${endpoint.method} ${endpoint.path}（${endpoint.summary}）`
    : `${endpoint.method} ${endpoint.path}`

  try {
    await ElMessageBox.confirm(
      `确定删除接口「${label}」吗？此操作不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    deletingId.value = endpoint.id
    await deleteApiEndpoint(props.project.id, endpoint.id)
    ElMessage.success('接口已删除')

    if (selectedEndpointId.value === endpoint.id) {
      detailDrawerVisible.value = false
      selectedEndpointId.value = null
    }

    if (endpoints.value.length === 1 && page.value > 1) {
      page.value -= 1
    }
    await loadEndpoints()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(getApiErrorMessage(error, '删除接口失败'))
    }
  } finally {
    deletingId.value = null
  }
}

function handlePageChange(nextPage: number): void {
  page.value = nextPage
  loadEndpoints()
}

function handleSizeChange(nextSize: number): void {
  pageSize.value = nextSize
  page.value = 1
  loadEndpoints()
}

watch(
  () => props.project.id,
  () => {
    page.value = 1
    loadEndpoints()
  },
)

onMounted(loadEndpoints)
</script>

<template>
  <div class="apis-tab">
    <div class="apis-toolbar">
      <div class="toolbar-tip">
        支持上传 OpenAPI 3.x 的 JSON / YAML 文件，重复导入将按 method + path 自动更新。
      </div>
      <el-upload
        ref="uploadRef"
        :show-file-list="false"
        accept=".json,.yaml,.yml"
        :disabled="uploading"
        :before-upload="handleUpload"
      >
        <el-button type="primary" :loading="uploading">上传 Swagger</el-button>
      </el-upload>
    </div>

    <AsyncState :loading="loading" :error="loadError" @retry="loadEndpoints">
    <el-table
      :data="endpoints"
      stripe
      empty-text="暂无接口，请上传 OpenAPI 文件"
    >
      <el-table-column label="方法" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="methodTagType(row.method)" size="small">
            {{ row.method }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="path" label="路径" min-width="220" show-overflow-tooltip />
      <el-table-column prop="summary" label="摘要" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.summary || '—' }}
        </template>
      </el-table-column>
      <el-table-column label="用例数" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row.test_case_count ? 'info' : ''" size="small">
            {{ row.test_case_count ?? 0 }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="导入时间" min-width="170">
        <template #default="{ row }">
          {{ formatBeijingTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openCreatePage(row.id)">新建用例</el-button>
          <el-button link type="success" @click="openGenerateDialog(row)">AI 生成</el-button>
          <el-button link type="primary" @click="openDetail(row)">详情</el-button>
          <el-button
            link
            type="danger"
            :loading="deletingId === row.id"
            @click="handleDelete(row)"
          >
            删除
          </el-button>
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

    <ApiEndpointDetailDrawer
      v-model:visible="detailDrawerVisible"
      :project-id="project.id"
      :endpoint-id="selectedEndpointId"
    />

    <AiGenerateDialog
      v-model:visible="generateDialogVisible"
      :project-id="project.id"
      :endpoint="generateEndpoint"
      @generated="handleGenerated"
    />
  </div>
</template>

<style scoped>
.apis-tab {
  margin-top: 8px;
}

.apis-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.toolbar-tip {
  color: #909399;
  font-size: 13px;
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
