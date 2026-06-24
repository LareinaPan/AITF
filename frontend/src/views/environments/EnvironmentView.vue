<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  createEnvironment,
  deleteEnvironment,
  fetchEnvironmentVariables,
  fetchEnvironments,
  saveEnvironmentVariables,
  updateEnvironment,
  type Environment,
  type EnvironmentVariablePayload,
} from '@/api/environments'
import { getApiErrorMessage } from '@/api/request'
import AsyncState from '@/components/common/AsyncState.vue'

interface VariableRow extends EnvironmentVariablePayload {
  _rowId: string
}

const loadingEnvironments = ref(false)
const environmentLoadError = ref<string | null>(null)
const loadingVariables = ref(false)
const saving = ref(false)
const submitting = ref(false)

const environments = ref<Environment[]>([])
const activeEnvironmentId = ref('')
const variableRows = ref<VariableRow[]>([])

const dialogVisible = ref(false)
const formRef = ref<FormInstance>()

const form = reactive({
  name: '',
  is_default: false,
})

const rules: FormRules = {
  name: [
    { required: true, message: '请输入环境名称', trigger: 'blur' },
    {
      pattern: /^[a-zA-Z0-9_-]{1,64}$/,
      message: '仅支持字母、数字、下划线、连字符',
      trigger: 'blur',
    },
  ],
}

const activeEnvironment = computed(() =>
  environments.value.find((item) => item.id === activeEnvironmentId.value),
)

function createRowId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function toVariableRows(variables: EnvironmentVariablePayload[]): VariableRow[] {
  return variables.map((item) => ({
    ...item,
    _rowId: createRowId(),
  }))
}

async function loadEnvironments(preferId?: string): Promise<void> {
  loadingEnvironments.value = true
  environmentLoadError.value = null
  try {
    environments.value = await fetchEnvironments()
    if (environments.value.length === 0) {
      activeEnvironmentId.value = ''
      variableRows.value = []
      return
    }

    const preferred = preferId ?? activeEnvironmentId.value
    const matched = environments.value.find((item) => item.id === preferred)
    const defaultEnv = environments.value.find((item) => item.is_default)
    activeEnvironmentId.value = matched?.id ?? defaultEnv?.id ?? environments.value[0].id
  } catch (error) {
    environmentLoadError.value = getApiErrorMessage(error, '加载环境列表失败')
  } finally {
    loadingEnvironments.value = false
  }
}

async function loadVariables(): Promise<void> {
  if (!activeEnvironmentId.value) {
    variableRows.value = []
    return
  }

  loadingVariables.value = true
  try {
    const variables = await fetchEnvironmentVariables(activeEnvironmentId.value)
    variableRows.value = toVariableRows(variables)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '加载环境变量失败'))
  } finally {
    loadingVariables.value = false
  }
}

function openCreateDialog(): void {
  form.name = ''
  form.is_default = environments.value.length === 0
  dialogVisible.value = true
}

async function handleCreateEnvironment(): Promise<void> {
  if (!formRef.value) {
    return
  }

  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) {
    return
  }

  submitting.value = true
  try {
    const created = await createEnvironment({
      name: form.name.trim(),
      is_default: form.is_default,
    })
    ElMessage.success('环境创建成功')
    dialogVisible.value = false
    await loadEnvironments(created.id)
    await loadVariables()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '创建环境失败'))
  } finally {
    submitting.value = false
  }
}

async function handleSetDefault(environment: Environment): Promise<void> {
  if (environment.is_default) {
    return
  }

  try {
    await updateEnvironment(environment.id, { is_default: true })
    ElMessage.success(`已将 ${environment.name} 设为默认环境`)
    await loadEnvironments(environment.id)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '设置默认环境失败'))
  }
}

async function handleDeleteEnvironment(environment: Environment): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定删除环境「${environment.name}」吗？关联变量将一并删除。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    await deleteEnvironment(environment.id)
    ElMessage.success('环境已删除')
    await loadEnvironments()
    await loadVariables()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(getApiErrorMessage(error, '删除环境失败'))
    }
  }
}

function addVariableRow(): void {
  variableRows.value.push({
    _rowId: createRowId(),
    key: '',
    value: '',
    is_secret: false,
  })
}

function removeVariableRow(rowId: string): void {
  variableRows.value = variableRows.value.filter((row) => row._rowId !== rowId)
}

async function handleSaveVariables(): Promise<void> {
  if (!activeEnvironmentId.value) {
    return
  }

  const payload: EnvironmentVariablePayload[] = []
  const keys = new Set<string>()

  for (const row of variableRows.value) {
    const key = row.key.trim()
    if (!key) {
      ElMessage.warning('变量 Key 不能为空')
      return
    }
    if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(key)) {
      ElMessage.warning(`变量 Key「${key}」格式不正确`)
      return
    }
    if (keys.has(key)) {
      ElMessage.warning(`变量 Key「${key}」重复`)
      return
    }
    keys.add(key)
    payload.push({
      key,
      value: row.value,
      is_secret: row.is_secret,
    })
  }

  saving.value = true
  try {
    const saved = await saveEnvironmentVariables(activeEnvironmentId.value, payload)
    variableRows.value = toVariableRows(saved)
    ElMessage.success('环境变量已保存')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '保存环境变量失败'))
  } finally {
    saving.value = false
  }
}

watch(activeEnvironmentId, loadVariables)

onMounted(async () => {
  await loadEnvironments()
  await loadVariables()
})
</script>

<template>
  <div class="environment-page">
    <el-card shadow="never">
      <template #header>
        <div class="page-header">
          <div>
            <h2 class="page-title">环境变量</h2>
            <p class="page-subtitle">
              全局环境配置，可在用例执行时通过
              <span v-pre>{{var}}</span>
              引用
            </p>
          </div>
          <el-button type="primary" @click="openCreateDialog">新建环境</el-button>
        </div>
      </template>

      <AsyncState
        :loading="loadingEnvironments"
        :error="environmentLoadError"
        @retry="loadEnvironments()"
      >
      <el-empty v-if="!loadingEnvironments && environments.length === 0" description="暂无环境，请先创建">
        <el-button type="primary" @click="openCreateDialog">创建 dev 环境</el-button>
      </el-empty>

      <template v-else>
        <div class="env-toolbar">
          <el-tabs v-model="activeEnvironmentId" class="env-tabs">
            <el-tab-pane
              v-for="environment in environments"
              :key="environment.id"
              :label="environment.is_default ? `${environment.name}（默认）` : environment.name"
              :name="environment.id"
            />
          </el-tabs>

          <div v-if="activeEnvironment" class="env-actions">
            <el-button
              v-if="!activeEnvironment.is_default"
              link
              type="primary"
              @click="handleSetDefault(activeEnvironment)"
            >
              设为默认
            </el-button>
            <el-button link type="danger" @click="handleDeleteEnvironment(activeEnvironment)">
              删除环境
            </el-button>
          </div>
        </div>

        <div v-loading="loadingVariables" class="variables-panel">
          <div class="variables-header">
            <span class="variables-title">Key-Value 变量</span>
            <div class="variables-actions">
              <el-button @click="addVariableRow">添加变量</el-button>
              <el-button type="primary" :loading="saving" @click="handleSaveVariables">
                保存变量
              </el-button>
            </div>
          </div>

          <p class="variables-tip">
            用例中的 <code v-pre>{{变量名}}</code> 将替换为当前环境配置的变量值。
            本地服务可填 <code>http://127.0.0.1:端口</code>（Docker 部署会自动映射到宿主机）；
            也可直接填 <code>http://host.docker.internal:端口</code>。
          </p>

          <el-table :data="variableRows" stripe empty-text="暂无变量，点击「添加变量」">
            <el-table-column label="Key" min-width="180">
              <template #default="{ row }">
                <el-input v-model="row.key" placeholder="如 base_url" />
              </template>
            </el-table-column>
            <el-table-column label="Value" min-width="280">
              <template #default="{ row }">
                <el-input
                  v-model="row.value"
                  :type="row.is_secret ? 'password' : 'text'"
                  placeholder="变量值"
                  show-password
                />
              </template>
            </el-table-column>
            <el-table-column label="敏感" width="100" align="center">
              <template #default="{ row }">
                <el-switch v-model="row.is_secret" />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100" align="center">
              <template #default="{ row }">
                <el-button link type="danger" @click="removeVariableRow(row._rowId)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
      </AsyncState>
    </el-card>

    <el-dialog v-model="dialogVisible" title="新建环境" width="420px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="环境名称" prop="name">
          <el-input v-model="form.name" placeholder="如 dev、test、staging" maxlength="64" />
        </el-form-item>
        <el-form-item label="设为默认环境">
          <el-switch v-model="form.is_default" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleCreateEnvironment">
          创建
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.page-subtitle {
  margin: 6px 0 0;
  color: #909399;
  font-size: 14px;
}

.env-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.env-tabs {
  flex: 1;
}

.env-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  padding-top: 6px;
}

.variables-panel {
  margin-top: 8px;
}

.variables-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.variables-title {
  font-size: 16px;
  font-weight: 600;
}

.variables-tip {
  margin: 0 0 12px;
  color: #909399;
  font-size: 13px;
  line-height: 1.6;
}

.variables-actions {
  display: flex;
  gap: 8px;
}
</style>
