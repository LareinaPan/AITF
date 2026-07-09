<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import { isAxiosError } from 'axios'

import type { PtProject } from '@/api/pt-projects'
import {
  createPtScenario,
  deletePtScenario,
  fetchPtScenarios,
  parseStatusLabel,
  parseStatusTagType,
  updatePtScenario,
  type PtScenario,
} from '@/api/pt-scenarios'
import { ptRunDetailPath, resolvePtRunLaunchTarget } from '@/api/pt-runs'
import { getApiErrorMessage } from '@/api/request'
import AsyncState from '@/components/common/AsyncState.vue'
import { formatBeijingTime } from '@/utils/datetime'

const props = defineProps<{
  project: PtProject
}>()

const router = useRouter()

const loading = ref(false)
const loadError = ref<string | null>(null)
const scenarios = ref<PtScenario[]>([])
const dialogVisible = ref(false)
const submitting = ref(false)
const editingScenario = ref<PtScenario | null>(null)
const formRef = ref<FormInstance>()
const runningScenarioId = ref<string | null>(null)

const form = reactive({
  name: '',
  description: '',
})

const rules: FormRules = {
  name: [
    { required: true, message: '请输入压测详情名称', trigger: 'blur' },
    { min: 1, max: 128, message: '名称长度为 1-128 个字符', trigger: 'blur' },
  ],
}

async function loadScenarios(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    scenarios.value = await fetchPtScenarios(props.project.id)
  } catch (error) {
    loadError.value = getApiErrorMessage(error, '加载压测详情列表失败')
  } finally {
    loading.value = false
  }
}

function openCreateDialog(): void {
  editingScenario.value = null
  form.name = ''
  form.description = ''
  dialogVisible.value = true
}

function openEditDialog(scenario: PtScenario): void {
  editingScenario.value = scenario
  form.name = scenario.name
  form.description = scenario.description ?? ''
  dialogVisible.value = true
}

async function handleSubmit(): Promise<void> {
  if (!formRef.value) {
    return
  }

  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) {
    return
  }

  submitting.value = true
  try {
    if (editingScenario.value) {
      await updatePtScenario(props.project.id, editingScenario.value.id, {
        name: form.name.trim(),
        description: form.description.trim() || null,
      })
      ElMessage.success('压测详情已更新')
    } else {
      await createPtScenario(props.project.id, {
        name: form.name.trim(),
        description: form.description.trim() || null,
      })
      ElMessage.success('压测详情创建成功')
    }
    dialogVisible.value = false
    await loadScenarios()
  } catch (error) {
    ElMessage.error(
      getApiErrorMessage(error, editingScenario.value ? '更新压测详情失败' : '创建压测详情失败'),
    )
  } finally {
    submitting.value = false
  }
}

async function handleDelete(scenario: PtScenario): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定删除压测详情「${scenario.name}」吗？关联脚本配置将一并删除。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    await deletePtScenario(props.project.id, scenario.id)
    ElMessage.success('压测详情已删除')
    await loadScenarios()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(getApiErrorMessage(error, '删除压测详情失败'))
    }
  }
}

async function handleRun(scenario: PtScenario): Promise<void> {
  if (scenario.parse_status !== 'success') {
    ElMessage.warning('请先上传并成功解析 JMX 脚本')
    return
  }

  runningScenarioId.value = scenario.id
  try {
    const target = await resolvePtRunLaunchTarget(props.project.id, scenario.id)
    await router.push(ptRunDetailPath(props.project.id, target.runId))
    ElMessage.success(
      target.redirected ? '已有压测在运行，已跳转到当前任务' : '压测已启动',
    )
  } catch (error) {
    if (isAxiosError(error) && error.response?.status === 409) {
      ElMessage.warning('已有压测任务在运行中，请等待完成或取消后再试')
      return
    }
    ElMessage.error(getApiErrorMessage(error, '启动压测失败'))
  } finally {
    runningScenarioId.value = null
  }
}

function handleConfigure(scenario: PtScenario): void {
  void router.push({
    name: 'pt-scenario-script',
    params: { id: props.project.id, scenarioId: scenario.id },
  })
}

onMounted(loadScenarios)
watch(
  () => props.project.id,
  () => {
    void loadScenarios()
  },
)
</script>

<template>
  <div class="pt-scenarios-tab">
    <AsyncState :loading="loading" :error="loadError" @retry="loadScenarios">
      <div class="tab-toolbar">
        <p class="tab-desc">管理压测场景，每个场景对应一份 JMeter 脚本配置</p>
        <el-button type="primary" @click="openCreateDialog">新建压测详情</el-button>
      </div>

      <el-table
        v-loading="loading"
        :data="scenarios"
        stripe
        empty-text="暂无压测详情，点击右上角新建"
      >
        <el-table-column prop="name" label="场景名称" min-width="160" />
        <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
        <el-table-column label="脚本状态" width="120">
          <template #default="{ row }">
            <el-tag :type="parseStatusTagType(row.parse_status)" size="small">
              {{ parseStatusLabel(row.parse_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最近运行" width="120">
          <template #default="{ row }">
            <span v-if="row.last_run_status">{{ row.last_run_status }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" min-width="170">
          <template #default="{ row }">
            {{ formatBeijingTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="handleConfigure(row)">配置脚本</el-button>
            <el-button
              link
              type="success"
              :loading="runningScenarioId === row.id"
              @click="handleRun(row)"
            >
              运行
            </el-button>
            <el-button link type="primary" @click="openEditDialog(row)">编辑</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-dialog
        v-model="dialogVisible"
        :title="editingScenario ? '编辑压测详情' : '新建压测详情'"
        width="480px"
        destroy-on-close
      >
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
          <el-form-item label="场景名称" prop="name">
            <el-input
              v-model="form.name"
              placeholder="如：登录接口压测"
              maxlength="128"
              show-word-limit
            />
          </el-form-item>
          <el-form-item label="场景描述">
            <el-input
              v-model="form.description"
              type="textarea"
              :rows="4"
              placeholder="可选，简要描述压测场景"
              maxlength="2000"
              show-word-limit
            />
          </el-form-item>
        </el-form>

        <template #footer>
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="submitting" @click="handleSubmit">
            {{ editingScenario ? '保存' : '创建' }}
          </el-button>
        </template>
      </el-dialog>
    </AsyncState>
  </div>
</template>

<style scoped>
.pt-scenarios-tab {
  margin-top: 8px;
}

.tab-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.tab-desc {
  margin: 0;
  color: #909399;
  font-size: 14px;
}

.muted {
  color: #c0c4cc;
}
</style>
