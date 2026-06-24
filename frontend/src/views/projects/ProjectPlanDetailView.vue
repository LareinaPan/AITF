<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'

import { fetchEnvironments, type Environment } from '@/api/environments'
import type { Project } from '@/api/projects'
import { getApiErrorMessage } from '@/api/request'
import { fetchTestCases, type TestCase } from '@/api/testCases'
import {
  bindPlanCases,
  fetchPlanRuns,
  fetchTestPlan,
  PLAN_CASE_MAX_COUNT,
  runTestPlan,
  unbindPlanCase,
  updateTestPlan,
  type PlanCaseItem,
  type PlanRun,
  type TestPlanDetail,
} from '@/api/testPlans'
import { formatBeijingTime } from '@/utils/datetime'
import { createCronFormRule } from '@/utils/cron'

const props = defineProps<{
  project: Project
}>()

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const submitting = ref(false)
const binding = ref(false)
const running = ref(false)
const plan = ref<TestPlanDetail | null>(null)
const planRuns = ref<PlanRun[]>([])
const environments = ref<Environment[]>([])
const allCases = ref<TestCase[]>([])

const editDialogVisible = ref(false)
const bindDialogVisible = ref(false)
const editFormRef = ref<FormInstance>()
const selectedCaseIds = ref<string[]>([])

const editForm = reactive({
  name: '',
  environment_id: '',
  cron_expression: '',
  is_enabled: false,
  notify_on_complete: true,
})

const editRules: FormRules = {
  name: [
    { required: true, message: '请输入计划名称', trigger: 'blur' },
    { min: 1, max: 128, message: '计划名称长度为 1-128 个字符', trigger: 'blur' },
  ],
  environment_id: [{ required: true, message: '请选择执行环境', trigger: 'change' }],
  cron_expression: [createCronFormRule({ requiredWhen: () => editForm.is_enabled })],
}

const planId = computed(() => route.params.planId as string)

const boundCaseIds = computed(() => new Set(plan.value?.cases.map((item) => item.case_id) ?? []))

const bindableCases = computed(() =>
  allCases.value.filter(
    (testCase) => testCase.status === 'active' && !boundCaseIds.value.has(testCase.id),
  ),
)

const remainingCapacity = computed(() =>
  Math.max(0, PLAN_CASE_MAX_COUNT - (plan.value?.case_count ?? 0)),
)

function statusLabel(status: string): string {
  return status === 'active' ? '正式' : '草稿'
}

function runStatusLabel(status: string): string {
  switch (status) {
    case 'running':
      return '执行中'
    case 'completed':
      return '成功'
    case 'failed':
      return '有失败'
    case 'pending':
      return '待执行'
    default:
      return status
  }
}

function runStatusTagType(status: string): 'success' | 'warning' | 'info' | 'danger' {
  switch (status) {
    case 'completed':
      return 'success'
    case 'failed':
      return 'danger'
    case 'running':
      return 'warning'
    default:
      return 'info'
  }
}

async function loadPlanRuns(): Promise<void> {
  try {
    planRuns.value = await fetchPlanRuns(props.project.id, planId.value)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '加载执行历史失败'))
  }
}

async function loadEnvironments(): Promise<void> {
  try {
    environments.value = await fetchEnvironments()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '加载环境列表失败'))
  }
}

async function loadAllCases(): Promise<void> {
  try {
    allCases.value = await fetchTestCases(props.project.id)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '加载用例列表失败'))
  }
}

async function loadPlan(): Promise<void> {
  loading.value = true
  try {
    plan.value = await fetchTestPlan(props.project.id, planId.value)
  } catch (error) {
    plan.value = null
    ElMessage.error(getApiErrorMessage(error, '加载计划详情失败'))
    await router.replace({ name: 'project-plans', params: { id: props.project.id } })
  } finally {
    loading.value = false
  }
}

function goBack(): void {
  router.push({ name: 'project-plans', params: { id: props.project.id } })
}

function openEditDialog(): void {
  if (!plan.value) {
    return
  }
  editForm.name = plan.value.name
  editForm.environment_id = plan.value.environment_id
  editForm.cron_expression = plan.value.cron_expression ?? ''
  editForm.is_enabled = plan.value.is_enabled
  editForm.notify_on_complete = plan.value.notify_on_complete
  editDialogVisible.value = true
}

async function handleUpdate(): Promise<void> {
  if (!editFormRef.value || !plan.value) {
    return
  }

  const valid = await editFormRef.value.validate().catch(() => false)
  if (!valid) {
    return
  }

  submitting.value = true
  try {
    await updateTestPlan(props.project.id, plan.value.id, {
      name: editForm.name.trim(),
      environment_id: editForm.environment_id,
      cron_expression: editForm.cron_expression.trim() || null,
      is_enabled: editForm.is_enabled,
      notify_on_complete: editForm.notify_on_complete,
    })
    ElMessage.success('计划已更新')
    editDialogVisible.value = false
    await loadPlan()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '更新计划失败'))
  } finally {
    submitting.value = false
  }
}

function openBindDialog(): void {
  if (!plan.value) {
    return
  }
  if (remainingCapacity.value === 0) {
    ElMessage.warning(`单个计划最多绑定 ${PLAN_CASE_MAX_COUNT} 条用例`)
    return
  }
  if (bindableCases.value.length === 0) {
    ElMessage.info('没有可绑定的正式用例')
    return
  }
  selectedCaseIds.value = []
  bindDialogVisible.value = true
}

function handleSelectionChange(rows: TestCase[]): void {
  selectedCaseIds.value = rows.map((row) => row.id)
}

async function handleBind(): Promise<void> {
  if (!plan.value) {
    return
  }
  if (selectedCaseIds.value.length === 0) {
    ElMessage.warning('请至少选择一条用例')
    return
  }
  if (selectedCaseIds.value.length > remainingCapacity.value) {
    ElMessage.warning(`最多还能绑定 ${remainingCapacity.value} 条用例`)
    return
  }

  binding.value = true
  try {
    plan.value = await bindPlanCases(props.project.id, plan.value.id, selectedCaseIds.value)
    ElMessage.success(`已绑定 ${selectedCaseIds.value.length} 条用例`)
    bindDialogVisible.value = false
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '绑定用例失败'))
  } finally {
    binding.value = false
  }
}

async function handleRunPlan(): Promise<void> {
  if (!plan.value) {
    return
  }
  if (plan.value.case_count === 0) {
    ElMessage.warning('请先绑定用例后再执行计划')
    return
  }

  running.value = true
  try {
    const run = await runTestPlan(props.project.id, plan.value.id)
    ElMessage.success(`计划执行完成：通过 ${run.pass_count}/${run.total_count}`)
    await loadPlanRuns()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '计划执行失败'))
  } finally {
    running.value = false
  }
}

async function handleUnbind(planCase: PlanCaseItem): Promise<void> {
  if (!plan.value) {
    return
  }

  try {
    await ElMessageBox.confirm(
      `确定从计划中移除用例「${planCase.case_name}」吗？`,
      '解绑确认',
      { type: 'warning', confirmButtonText: '移除', cancelButtonText: '取消' },
    )
    plan.value = await unbindPlanCase(props.project.id, plan.value.id, planCase.case_id)
    ElMessage.success('用例已解绑')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(getApiErrorMessage(error, '解绑用例失败'))
    }
  }
}

watch(planId, () => {
  loadPlan()
  loadPlanRuns()
})

watch(
  () => props.project.id,
  () => {
    loadAllCases()
    loadPlan()
    loadPlanRuns()
  },
)

watch(
  () => editForm.is_enabled,
  () => {
    editFormRef.value?.validateField('cron_expression').catch(() => undefined)
  },
)

onMounted(async () => {
  await Promise.all([loadEnvironments(), loadAllCases(), loadPlan(), loadPlanRuns()])
})
</script>

<template>
  <div v-loading="loading || running" :element-loading-text="running ? '计划执行中，请稍候...' : undefined" class="plan-detail-page">
    <el-page-header @back="goBack">
      <template #content>
        <span class="plan-title">{{ plan?.name ?? '计划详情' }}</span>
      </template>
      <template #extra>
        <el-button v-if="plan" :loading="running" type="success" @click="handleRunPlan">
          执行计划
        </el-button>
        <el-button v-if="plan" @click="openEditDialog">编辑计划</el-button>
        <el-button v-if="plan" type="primary" @click="openBindDialog">绑定用例</el-button>
      </template>
    </el-page-header>

    <el-card v-if="plan" shadow="never" class="info-card">
      <el-descriptions :column="2" border>
        <el-descriptions-item label="执行环境">
          {{ plan.environment_name }}
        </el-descriptions-item>
        <el-descriptions-item label="用例数">
          {{ plan.case_count }} / {{ PLAN_CASE_MAX_COUNT }}
        </el-descriptions-item>
        <el-descriptions-item label="Cron 表达式">
          {{ plan.cron_expression || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="定时任务">
          <el-tag :type="plan.is_enabled ? 'success' : 'info'" size="small">
            {{ plan.is_enabled ? '启用' : '关闭' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="结果通知">
          <el-tag :type="plan.notify_on_complete ? 'success' : 'info'" size="small">
            {{ plan.notify_on_complete ? '开启' : '关闭' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="创建时间" :span="2">
          {{ formatBeijingTime(plan.created_at) }}
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card v-if="plan" shadow="never" class="cases-card">
      <template #header>
        <div class="cases-card-header">
          <span>已绑定用例（按执行顺序）</span>
          <span class="cases-hint">仅支持绑定「正式」状态用例</span>
        </div>
      </template>

      <el-table :data="plan.cases" stripe empty-text="暂未绑定用例，点击右上角绑定">
        <el-table-column label="顺序" width="80" align="center">
          <template #default="{ row }">
            {{ row.sort_order + 1 }}
          </template>
        </el-table-column>
        <el-table-column prop="case_name" label="用例名称" min-width="200" show-overflow-tooltip />
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" @click="handleUnbind(row)">解绑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="plan" shadow="never" class="runs-card">
      <template #header>
        <span>执行历史</span>
      </template>
      <el-table :data="planRuns" stripe empty-text="暂无执行记录">
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="runStatusTagType(row.status)" size="small">
              {{ runStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="结果" width="140" align="center">
          <template #default="{ row }">
            {{ row.pass_count }}/{{ row.total_count }} 通过
            <span v-if="row.fail_count > 0" class="fail-count">（{{ row.fail_count }} 失败）</span>
          </template>
        </el-table-column>
        <el-table-column label="开始时间" min-width="170">
          <template #default="{ row }">
            {{ row.started_at ? formatBeijingTime(row.started_at) : '—' }}
          </template>
        </el-table-column>
        <el-table-column label="结束时间" min-width="170">
          <template #default="{ row }">
            {{ row.finished_at ? formatBeijingTime(row.finished_at) : '—' }}
          </template>
        </el-table-column>
        <el-table-column label="报告" width="120" fixed="right">
          <template #default="{ row }">
            <el-link
              v-if="row.allure_report_url"
              :href="row.allure_report_url"
              target="_blank"
              type="primary"
            >
              查看报告
            </el-link>
            <span v-else>—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="editDialogVisible" title="编辑测试计划" width="520px" destroy-on-close>
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="100px">
        <el-form-item label="计划名称" prop="name">
          <el-input v-model="editForm.name" maxlength="128" show-word-limit />
        </el-form-item>
        <el-form-item label="执行环境" prop="environment_id">
          <el-select
            v-model="editForm.environment_id"
            placeholder="选择环境"
            style="width: 100%"
            :disabled="environments.length === 0"
          >
            <el-option
              v-for="environment in environments"
              :key="environment.id"
              :label="environment.is_default ? `${environment.name}（默认）` : environment.name"
              :value="environment.id"
            />
          </el-select>
          <p class="field-hint">计划执行时将使用该环境的变量（如 base_url、token）</p>
        </el-form-item>
        <el-form-item label="Cron" prop="cron_expression">
          <el-input
            v-model="editForm.cron_expression"
            placeholder="5 段格式：分 时 日 月 周，如 50 10 * * 1-5（北京时间，周一至周五 10:50）"
          />
        </el-form-item>
        <el-form-item label="启用定时">
          <el-switch v-model="editForm.is_enabled" />
        </el-form-item>
        <el-form-item label="结果通知">
          <el-switch v-model="editForm.notify_on_complete" />
          <p class="field-hint">
            开启后，计划执行完成时将向接口项目设置中的 Webhook 地址发送结果摘要
          </p>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleUpdate">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="bindDialogVisible"
      title="绑定用例"
      width="720px"
      destroy-on-close
    >
      <p class="bind-hint">
        还可绑定 {{ remainingCapacity }} 条用例（仅显示未绑定的正式用例）
      </p>
      <el-table
        :data="bindableCases"
        max-height="360"
        stripe
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="48" />
        <el-table-column prop="name" label="用例名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="priority" label="优先级" width="100" align="center" />
        <el-table-column label="状态" width="100" align="center">
          <template #default>
            <el-tag type="success" size="small">正式</el-tag>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="bindDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="binding" @click="handleBind">
          绑定所选（{{ selectedCaseIds.length }}）
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.plan-detail-page {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.plan-title {
  font-size: 18px;
  font-weight: 600;
}

.info-card,
.cases-card,
.runs-card {
  margin-top: 0;
}

.cases-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.cases-hint,
.bind-hint {
  margin: 0 0 12px;
  color: #909399;
  font-size: 13px;
}

.cases-hint {
  margin-bottom: 0;
}

.field-hint {
  margin: 6px 0 0;
  color: #909399;
  font-size: 12px;
  line-height: 1.4;
}

.fail-count {
  color: #f56c6c;
}
</style>
