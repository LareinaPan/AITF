<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { fetchAllApiEndpoints, methodTagType, type ApiEndpoint } from '@/api/apiEndpoints'
import { fetchEnvironments, type Environment } from '@/api/environments'
import type { Project } from '@/api/projects'
import { getApiErrorMessage } from '@/api/request'
import {
  deleteTestCase,
  fetchTestCases,
  runTestCase,
  type TestCase,
  type TestCasePriority,
  type TestCaseRunResult,
  type TestCaseStatus,
} from '@/api/testCases'
import TestCaseRunResultDrawer from '@/components/testcases/TestCaseRunResultDrawer.vue'
import { formatBeijingTime } from '@/utils/datetime'

const UNLINKED_GROUP_ID = '__unlinked__'

interface ApiCaseGroup {
  id: string
  method: string
  path: string
  summary: string | null
  cases: TestCase[]
}

const props = defineProps<{
  project: Project
}>()

const router = useRouter()

const loading = ref(false)
const runningCaseId = ref<string | null>(null)
const endpoints = ref<ApiEndpoint[]>([])
const testCases = ref<TestCase[]>([])
const environments = ref<Environment[]>([])
const selectedEnvironmentId = ref('')

const runDrawerVisible = ref(false)
const runResult = ref<TestCaseRunResult | null>(null)
const runLoading = ref(false)

const filterPriority = ref<TestCasePriority | ''>('')
const filterStatus = ref<TestCaseStatus | ''>('')

const priorityOptions: TestCasePriority[] = ['P0', 'P1', 'P2', 'P3']

function filterCase(item: TestCase): boolean {
  if (filterPriority.value && item.priority !== filterPriority.value) {
    return false
  }
  if (filterStatus.value && item.status !== filterStatus.value) {
    return false
  }
  return true
}

const groupedCases = computed<ApiCaseGroup[]>(() => {
  const casesByApi = new Map<string, TestCase[]>()
  const unlinkedCases: TestCase[] = []

  for (const testCase of testCases.value) {
    if (!filterCase(testCase)) {
      continue
    }
    if (testCase.api_endpoint_id) {
      const current = casesByApi.get(testCase.api_endpoint_id) ?? []
      current.push(testCase)
      casesByApi.set(testCase.api_endpoint_id, current)
      continue
    }
    unlinkedCases.push(testCase)
  }

  const groups: ApiCaseGroup[] = endpoints.value
    .map((endpoint) => ({
      id: endpoint.id,
      method: endpoint.method,
      path: endpoint.path,
      summary: endpoint.summary,
      cases: casesByApi.get(endpoint.id) ?? [],
    }))
    .filter((group) => group.cases.length > 0)

  if (unlinkedCases.length > 0) {
    groups.push({
      id: UNLINKED_GROUP_ID,
      method: '—',
      path: '未关联接口',
      summary: null,
      cases: unlinkedCases,
    })
  }

  return groups
})

const totalVisibleCases = computed(() =>
  groupedCases.value.reduce((count, group) => count + group.cases.length, 0),
)

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

function statusLabel(status: TestCaseStatus): string {
  return status === 'active' ? '正式' : '草稿'
}

function statusTagType(status: TestCaseStatus): 'success' | 'info' {
  return status === 'active' ? 'success' : 'info'
}

async function loadEnvironments(): Promise<void> {
  try {
    environments.value = await fetchEnvironments()
    if (environments.value.length === 0) {
      selectedEnvironmentId.value = ''
      return
    }
    const current = environments.value.find((item) => item.id === selectedEnvironmentId.value)
    const defaultEnv = environments.value.find((item) => item.is_default)
    selectedEnvironmentId.value = current?.id ?? defaultEnv?.id ?? environments.value[0].id
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '加载环境列表失败'))
  }
}

async function loadData(): Promise<void> {
  loading.value = true
  try {
    const [endpointList, caseList] = await Promise.all([
      fetchAllApiEndpoints(props.project.id),
      fetchTestCases(props.project.id),
    ])
    endpoints.value = endpointList
    testCases.value = caseList
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '加载用例列表失败'))
  } finally {
    loading.value = false
  }
}

function openCreatePage(apiId?: string): void {
  router.push({
    name: 'project-case-create',
    params: { id: props.project.id },
    query: apiId ? { apiId } : undefined,
  })
}

function openEditPage(testCase: TestCase): void {
  router.push({
    name: 'project-case-edit',
    params: { id: props.project.id, caseId: testCase.id },
  })
}

async function handleRun(testCase: TestCase): Promise<void> {
  if (!selectedEnvironmentId.value) {
    ElMessage.warning('请先创建并选择执行环境')
    return
  }

  const environment = environments.value.find((item) => item.id === selectedEnvironmentId.value)

  runningCaseId.value = testCase.id
  runResult.value = null
  runDrawerVisible.value = true
  runLoading.value = true

  try {
    runResult.value = await runTestCase(
      props.project.id,
      testCase.id,
      selectedEnvironmentId.value,
    )
    if (!runResult.value.passed) {
      ElMessage.warning('用例执行完成，但未通过断言')
    }
  } catch (error) {
    runResult.value = {
      case_id: testCase.id,
      case_name: testCase.name,
      environment_id: selectedEnvironmentId.value,
      environment_name: environment?.name ?? '未知环境',
      passed: false,
      error: getApiErrorMessage(error, '用例执行失败'),
      prepared_request: {
        method: testCase.request_json.method,
        url: testCase.request_json.url,
        headers: {},
        params: {},
        body_type: testCase.request_json.body.type,
        body_content: testCase.request_json.body.content,
      },
      response: null,
      assertions: null,
    }
    ElMessage.error(getApiErrorMessage(error, '用例执行失败'))
  } finally {
    runLoading.value = false
    runningCaseId.value = null
  }
}

async function handleDelete(testCase: TestCase): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定删除用例「${testCase.name}」吗？此操作不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    await deleteTestCase(props.project.id, testCase.id)
    ElMessage.success('用例已删除')
    await loadData()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(getApiErrorMessage(error, '删除用例失败'))
    }
  }
}

watch(
  () => props.project.id,
  () => {
    filterPriority.value = ''
    filterStatus.value = ''
    loadData()
  },
)

onMounted(async () => {
  await Promise.all([loadEnvironments(), loadData()])
})
</script>

<template>
  <div class="cases-tab">
    <div class="cases-toolbar">
      <div class="filters">
        <el-select
          v-model="selectedEnvironmentId"
          placeholder="执行环境"
          style="width: 160px"
          :disabled="environments.length === 0"
        >
          <el-option
            v-for="environment in environments"
            :key="environment.id"
            :label="environment.is_default ? `${environment.name}（默认）` : environment.name"
            :value="environment.id"
          />
        </el-select>
        <el-select v-model="filterPriority" clearable placeholder="优先级" style="width: 120px">
          <el-option v-for="item in priorityOptions" :key="item" :label="item" :value="item" />
        </el-select>
        <el-select v-model="filterStatus" clearable placeholder="状态" style="width: 120px">
          <el-option label="正式" value="active" />
          <el-option label="草稿" value="draft" />
        </el-select>
      </div>
      <el-button type="primary" @click="openCreatePage()">新建用例</el-button>
    </div>

    <el-table
      v-loading="loading"
      :data="groupedCases"
      row-key="id"
      default-expand-all
      empty-text="暂无用例，可在接口管理下新建或 AI 生成"
    >
      <el-table-column type="expand">
        <template #default="{ row }">
          <div class="nested-table-wrap">
            <el-table :data="row.cases" size="small" stripe>
              <el-table-column prop="name" label="用例名称" min-width="180" show-overflow-tooltip />
              <el-table-column label="优先级" width="100" align="center">
                <template #default="{ row: testCase }">
                  <el-tag :type="priorityTagType(testCase.priority)" size="small">
                    {{ testCase.priority }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="100" align="center">
                <template #default="{ row: testCase }">
                  <el-tag :type="statusTagType(testCase.status)" size="small">
                    {{ statusLabel(testCase.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="创建时间" min-width="170">
                <template #default="{ row: testCase }">
                  {{ formatBeijingTime(testCase.created_at) }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="200" fixed="right">
                <template #default="{ row: testCase }">
                  <el-button
                    link
                    type="success"
                    :loading="runningCaseId === testCase.id"
                    @click="handleRun(testCase)"
                  >
                    执行
                  </el-button>
                  <el-button link type="primary" @click="openEditPage(testCase)">编辑</el-button>
                  <el-button link type="danger" @click="handleDelete(testCase)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="方法" width="100" align="center">
        <template #default="{ row }">
          <el-tag
            v-if="row.id !== UNLINKED_GROUP_ID"
            :type="methodTagType(row.method)"
            size="small"
          >
            {{ row.method }}
          </el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column prop="path" label="接口路径" min-width="220" show-overflow-tooltip />
      <el-table-column label="摘要" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.summary || '—' }}
        </template>
      </el-table-column>
      <el-table-column label="用例数" width="100" align="center">
        <template #default="{ row }">
          <el-tag type="info" size="small">{{ row.cases.length }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.id !== UNLINKED_GROUP_ID"
            link
            type="primary"
            @click="openCreatePage(row.id)"
          >
            新建用例
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="totalVisibleCases > 0" class="cases-summary">
      共 {{ groupedCases.length }} 个接口分组，{{ totalVisibleCases }} 条用例
    </div>

    <TestCaseRunResultDrawer
      v-model:visible="runDrawerVisible"
      :result="runResult"
      :running="runLoading"
    />
  </div>
</template>

<style scoped>
.cases-tab {
  margin-top: 8px;
}

.cases-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.filters {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.nested-table-wrap {
  padding: 4px 12px 12px 48px;
}

.cases-summary {
  margin-top: 12px;
  color: #909399;
  font-size: 13px;
  text-align: right;
}
</style>
