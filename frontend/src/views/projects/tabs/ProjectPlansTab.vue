<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'

import { fetchEnvironments, type Environment } from '@/api/environments'
import type { Project } from '@/api/projects'
import { getApiErrorMessage } from '@/api/request'
import {
  createTestPlan,
  deleteTestPlan,
  fetchTestPlans,
  type TestPlan,
} from '@/api/testPlans'
import { formatBeijingTime } from '@/utils/datetime'
import { createCronFormRule } from '@/utils/cron'

const props = defineProps<{
  project: Project
}>()

const router = useRouter()

const loading = ref(false)
const submitting = ref(false)
const plans = ref<TestPlan[]>([])
const environments = ref<Environment[]>([])
const dialogVisible = ref(false)
const formRef = ref<FormInstance>()

const form = reactive({
  name: '',
  environment_id: '',
  cron_expression: '',
  is_enabled: false,
})

const rules: FormRules = {
  name: [
    { required: true, message: '请输入计划名称', trigger: 'blur' },
    { min: 1, max: 128, message: '计划名称长度为 1-128 个字符', trigger: 'blur' },
  ],
  environment_id: [{ required: true, message: '请选择执行环境', trigger: 'change' }],
  cron_expression: [createCronFormRule({ requiredWhen: () => form.is_enabled })],
}

function goToEnvironments(): void {
  router.push('/environments')
}

async function loadEnvironments(): Promise<void> {
  try {
    environments.value = await fetchEnvironments()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '加载环境列表失败'))
  }
}

async function loadPlans(): Promise<void> {
  loading.value = true
  try {
    plans.value = await fetchTestPlans(props.project.id)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '加载测试计划失败'))
  } finally {
    loading.value = false
  }
}

function openCreateDialog(): void {
  if (environments.value.length === 0) {
    ElMessage.warning('请先在「环境变量」页面创建执行环境')
    return
  }

  form.name = ''
  form.cron_expression = ''
  form.is_enabled = false
  const defaultEnv = environments.value.find((item) => item.is_default)
  form.environment_id = defaultEnv?.id ?? environments.value[0].id
  dialogVisible.value = true
}

async function handleCreate(): Promise<void> {
  if (!formRef.value) {
    return
  }

  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) {
    return
  }

  submitting.value = true
  try {
    const plan = await createTestPlan(props.project.id, {
      name: form.name.trim(),
      environment_id: form.environment_id,
      cron_expression: form.cron_expression.trim() || null,
      is_enabled: form.is_enabled,
    })
    ElMessage.success('测试计划已创建')
    dialogVisible.value = false
    await router.push({
      name: 'project-plan-detail',
      params: { id: props.project.id, planId: plan.id },
    })
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '创建测试计划失败'))
  } finally {
    submitting.value = false
  }
}

function openDetail(plan: TestPlan): void {
  router.push({
    name: 'project-plan-detail',
    params: { id: props.project.id, planId: plan.id },
  })
}

async function handleDelete(plan: TestPlan): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定删除计划「${plan.name}」吗？已绑定的用例关联将一并移除。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    await deleteTestPlan(props.project.id, plan.id)
    ElMessage.success('测试计划已删除')
    await loadPlans()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(getApiErrorMessage(error, '删除测试计划失败'))
    }
  }
}

watch(
  () => props.project.id,
  () => {
    loadPlans()
  },
)

watch(
  () => form.is_enabled,
  () => {
    formRef.value?.validateField('cron_expression').catch(() => undefined)
  },
)

onMounted(async () => {
  await Promise.all([loadEnvironments(), loadPlans()])
})
</script>

<template>
  <div class="plans-tab">
    <div class="plans-toolbar">
      <p class="plans-hint">将多条正式用例编排为测试计划，后续可手动或定时执行。</p>
      <el-button type="primary" @click="openCreateDialog">新建计划</el-button>
    </div>

    <el-alert
      v-if="environments.length === 0"
      type="warning"
      :closable="false"
      show-icon
      class="env-alert"
      title="尚未配置执行环境"
      description="测试计划必须关联执行环境（用于 base_url、token 等变量）。请先创建环境后再新建计划。"
    >
      <el-button type="primary" link @click="goToEnvironments">前往环境变量页面</el-button>
    </el-alert>

    <el-table
      v-loading="loading"
      :data="plans"
      stripe
      empty-text="暂无测试计划，点击右上角新建"
    >
      <el-table-column prop="name" label="计划名称" min-width="180" show-overflow-tooltip />
      <el-table-column label="执行环境" min-width="140">
        <template #default="{ row }">
          {{ row.environment_name }}
        </template>
      </el-table-column>
      <el-table-column label="用例数" width="100" align="center">
        <template #default="{ row }">
          <el-tag type="info" size="small">{{ row.case_count }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="Cron" min-width="140" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.cron_expression || '—' }}
        </template>
      </el-table-column>
      <el-table-column label="定时" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row.is_enabled ? 'success' : 'info'" size="small">
            {{ row.is_enabled ? '启用' : '关闭' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" min-width="170">
        <template #default="{ row }">
          {{ formatBeijingTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDetail(row)">详情</el-button>
          <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新建测试计划" width="520px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="计划名称" prop="name">
          <el-input v-model="form.name" maxlength="128" show-word-limit placeholder="如：冒烟测试" />
        </el-form-item>
        <el-form-item label="执行环境" prop="environment_id">
          <el-select
            v-model="form.environment_id"
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
            v-model="form.cron_expression"
            placeholder="5 段格式：分 时 日 月 周，如 50 10 * * 1-5（北京时间，周一至周五 10:50）"
          />
        </el-form-item>
        <el-form-item label="启用定时">
          <el-switch v-model="form.is_enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.plans-tab {
  margin-top: 8px;
}

.plans-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.plans-hint {
  margin: 0;
  color: #909399;
  font-size: 13px;
}

.env-alert {
  margin-bottom: 16px;
}

.field-hint {
  margin: 6px 0 0;
  color: #909399;
  font-size: 12px;
  line-height: 1.4;
}
</style>
