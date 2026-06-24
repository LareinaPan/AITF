<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'

import { fetchAllApiEndpoints, type ApiEndpoint } from '@/api/apiEndpoints'
import { fetchEnvironments, type Environment } from '@/api/environments'
import type { Project } from '@/api/projects'
import { getApiErrorMessage } from '@/api/request'
import {
  buildRequestPayload,
  createDefaultAssertionsJson,
  createDefaultRequestJson,
  createTestCase,
  fetchTestCase,
  runTestCase,
  updateTestCase,
  type TestCase,
  type TestCaseAssertionsJson,
  type TestCasePriority,
  type TestCaseRequestJson,
  type TestCaseRunResult,
} from '@/api/testCases'
import TestCaseAssertionsEditor from '@/components/testcases/TestCaseAssertionsEditor.vue'
import TestCaseRequestEditor from '@/components/testcases/TestCaseRequestEditor.vue'
import TestCaseRunResultDrawer from '@/components/testcases/TestCaseRunResultDrawer.vue'

const props = defineProps<{
  project: Project
}>()

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const saving = ref(false)
const running = ref(false)
const formRef = ref<FormInstance>()
const endpoints = ref<ApiEndpoint[]>([])
const environments = ref<Environment[]>([])
const selectedEnvironmentId = ref('')
const savedTestCase = ref<TestCase | null>(null)

const runDrawerVisible = ref(false)
const runResult = ref<TestCaseRunResult | null>(null)
const runLoading = ref(false)

const isEditMode = computed(() => route.name === 'project-case-edit')
const caseId = computed(() => route.params.caseId as string | undefined)
const initialApiId = computed(() => route.query.apiId as string | undefined)

const form = reactive({
  name: '',
  description: '',
  priority: 'P2' as TestCasePriority,
  apiEndpointId: '',
})

const requestJson = ref<TestCaseRequestJson>(createDefaultRequestJson())
const assertionsJson = ref<TestCaseAssertionsJson>(createDefaultAssertionsJson())
const requestEditorRef = ref<InstanceType<typeof TestCaseRequestEditor> | null>(null)
const assertionsEditorRef = ref<InstanceType<typeof TestCaseAssertionsEditor> | null>(null)
const editorKey = ref(0)

const priorityOptions: TestCasePriority[] = ['P0', 'P1', 'P2', 'P3']

const rules: FormRules = {
  name: [
    { required: true, message: '请输入用例名称', trigger: 'blur' },
    { min: 1, max: 128, message: '用例名称长度为 1-128 个字符', trigger: 'blur' },
  ],
  apiEndpointId: [{ required: true, message: '请选择关联接口', trigger: 'change' }],
}

const pageTitle = computed(() => (isEditMode.value ? '编辑用例' : '新建用例'))

const selectedEndpoint = computed(() =>
  endpoints.value.find((item) => item.id === form.apiEndpointId) ?? null,
)

function endpointLabel(endpoint: ApiEndpoint): string {
  const summary = endpoint.summary ? ` — ${endpoint.summary}` : ''
  return `${endpoint.method} ${endpoint.path}${summary}`
}

function applyEndpointDefaults(endpoint: ApiEndpoint): void {
  requestJson.value = {
    ...requestJson.value,
    method: endpoint.method,
    url: `{{base_url}}${endpoint.path}`,
  }
  editorKey.value += 1
}

function backToList(): void {
  router.push({ name: 'project-cases', params: { id: props.project.id } })
}

async function loadEnvironments(): Promise<void> {
  try {
    environments.value = await fetchEnvironments()
    if (environments.value.length === 0) {
      selectedEnvironmentId.value = ''
      return
    }
    const defaultEnv = environments.value.find((item) => item.is_default)
    selectedEnvironmentId.value = defaultEnv?.id ?? environments.value[0].id
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '加载环境列表失败'))
  }
}

async function loadEndpoints(): Promise<void> {
  try {
    endpoints.value = await fetchAllApiEndpoints(props.project.id)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '加载接口列表失败'))
  }
}

async function loadTestCase(): Promise<void> {
  if (!isEditMode.value || !caseId.value) {
    requestJson.value = createDefaultRequestJson()
    assertionsJson.value = createDefaultAssertionsJson()
    if (initialApiId.value) {
      form.apiEndpointId = initialApiId.value
      const endpoint = endpoints.value.find((item) => item.id === initialApiId.value)
      if (endpoint) {
        applyEndpointDefaults(endpoint)
      }
    }
    return
  }

  loading.value = true
  try {
    const testCase = await fetchTestCase(props.project.id, caseId.value)
    savedTestCase.value = testCase
    form.name = testCase.name
    form.description = testCase.description ?? ''
    form.priority = testCase.priority
    form.apiEndpointId = testCase.api_endpoint_id ?? ''
    requestJson.value = { ...testCase.request_json }
    assertionsJson.value = { ...testCase.assertions_json }
    editorKey.value += 1
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '加载用例失败'))
    backToList()
  } finally {
    loading.value = false
  }
}

function handleEndpointChange(endpointId: string): void {
  const endpoint = endpoints.value.find((item) => item.id === endpointId)
  if (!endpoint || isEditMode.value) {
    return
  }
  applyEndpointDefaults(endpoint)
}

async function handleSave(): Promise<void> {
  if (!formRef.value) {
    return
  }

  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) {
    return
  }

  const currentRequest =
    requestEditorRef.value?.getCurrentRequestJson() ?? requestJson.value
  const currentAssertions =
    assertionsEditorRef.value?.getCurrentAssertionsJson() ?? assertionsJson.value

  if (!currentRequest.url.trim()) {
    ElMessage.warning('请输入请求 URL')
    return
  }

  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      priority: form.priority,
      api_endpoint_id: form.apiEndpointId,
      request_json: buildRequestPayload(currentRequest),
      assertions_json: currentAssertions,
    }

    if (isEditMode.value && caseId.value) {
      const updated = await updateTestCase(props.project.id, caseId.value, payload)
      savedTestCase.value = updated
      ElMessage.success('用例已保存')
    } else {
      await createTestCase(props.project.id, {
        ...payload,
        status: 'active',
      })
      ElMessage.success('用例创建成功')
    }
    backToList()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '保存用例失败'))
  } finally {
    saving.value = false
  }
}

async function handleRun(): Promise<void> {
  if (!isEditMode.value || !caseId.value || !savedTestCase.value) {
    return
  }

  if (!selectedEnvironmentId.value) {
    ElMessage.warning('请先创建并选择执行环境')
    return
  }

  const testCase = savedTestCase.value
  const environment = environments.value.find((item) => item.id === selectedEnvironmentId.value)

  running.value = true
  runResult.value = null
  runDrawerVisible.value = true
  runLoading.value = true

  try {
    runResult.value = await runTestCase(
      props.project.id,
      caseId.value,
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
    running.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadEnvironments(), loadEndpoints()])
  await loadTestCase()
})
</script>

<template>
  <div v-loading="loading || running" :element-loading-text="running ? '用例执行中，请稍候...' : undefined" class="case-editor">
    <div class="editor-header">
      <div>
        <h3 class="editor-title">{{ pageTitle }}</h3>
        <p class="editor-subtitle">配置 HTTP 请求与断言规则，用例需关联到具体接口</p>
      </div>
      <div class="editor-actions">
        <el-select
          v-if="isEditMode"
          v-model="selectedEnvironmentId"
          placeholder="执行环境"
          style="width: 160px"
          :disabled="environments.length === 0 || running"
        >
          <el-option
            v-for="environment in environments"
            :key="environment.id"
            :label="environment.is_default ? `${environment.name}（默认）` : environment.name"
            :value="environment.id"
          />
        </el-select>
        <el-button
          v-if="isEditMode"
          type="success"
          :loading="running"
          :disabled="environments.length === 0"
          @click="handleRun"
        >
          运行
        </el-button>
        <el-button @click="backToList">返回列表</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </div>
    </div>

    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="meta-form">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="用例名称" prop="name">
            <el-input v-model="form.name" placeholder="如：登录成功" maxlength="128" show-word-limit />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="优先级">
            <el-select v-model="form.priority" style="width: 100%">
              <el-option v-for="item in priorityOptions" :key="item" :label="item" :value="item" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="关联接口" prop="apiEndpointId">
        <el-select
          v-model="form.apiEndpointId"
          filterable
          placeholder="请选择接口"
          style="width: 100%"
          :disabled="endpoints.length === 0"
          @change="handleEndpointChange"
        >
          <el-option
            v-for="endpoint in endpoints"
            :key="endpoint.id"
            :label="endpointLabel(endpoint)"
            :value="endpoint.id"
          />
        </el-select>
        <p v-if="endpoints.length === 0" class="field-tip">
          暂无接口，请先在「接口管理」上传 OpenAPI 文件。
        </p>
        <p v-else-if="selectedEndpoint" class="field-tip">
          当前关联：{{ selectedEndpoint.method }} {{ selectedEndpoint.path }}
        </p>
      </el-form-item>
      <el-form-item label="描述">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="2"
          placeholder="可选"
          maxlength="2000"
          show-word-limit
        />
      </el-form-item>
    </el-form>

    <el-card shadow="never" class="section-card">
      <template #header>
        <span class="card-title">请求配置</span>
      </template>
      <TestCaseRequestEditor
        :key="`request-${editorKey}`"
        ref="requestEditorRef"
        v-model="requestJson"
      />
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>
        <span class="card-title">断言配置</span>
      </template>
      <TestCaseAssertionsEditor
        :key="`assertions-${editorKey}`"
        ref="assertionsEditorRef"
        v-model="assertionsJson"
      />
    </el-card>

    <TestCaseRunResultDrawer
      v-model:visible="runDrawerVisible"
      :result="runResult"
      :running="runLoading"
    />
  </div>
</template>

<style scoped>
.case-editor {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.editor-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.editor-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.editor-subtitle {
  margin: 6px 0 0;
  color: #909399;
  font-size: 13px;
}

.editor-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.meta-form {
  margin-bottom: 0;
}

.field-tip {
  margin: 6px 0 0;
  color: #909399;
  font-size: 12px;
}

.section-card {
  border: 1px solid #ebeef5;
}

.card-title {
  font-weight: 600;
}
</style>
