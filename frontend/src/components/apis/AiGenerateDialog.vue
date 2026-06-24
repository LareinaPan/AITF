<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import {
  DEFAULT_AI_GENERATE_COUNTS,
  generateAiTestCases,
  getTotalGenerateCount,
  methodTagType,
  type AIGeneratePayload,
  type AIGenerateResult,
  type ApiEndpoint,
} from '@/api/apiEndpoints'
import { getApiErrorMessage } from '@/api/request'

const props = defineProps<{
  visible: boolean
  projectId: string
  endpoint: ApiEndpoint | null
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  generated: [result: AIGenerateResult]
}>()

const formRef = ref<FormInstance>()
const generating = ref(false)

const form = reactive<AIGeneratePayload>({ ...DEFAULT_AI_GENERATE_COUNTS })

const dialogVisible = computed({
  get: () => props.visible,
  set: (value: boolean) => emit('update:visible', value),
})

const totalCount = computed(() => getTotalGenerateCount(form))

const endpointLabel = computed(() => {
  if (!props.endpoint) {
    return ''
  }
  const summary = props.endpoint.summary ? ` — ${props.endpoint.summary}` : ''
  return `${props.endpoint.method} ${props.endpoint.path}${summary}`
})

const rules: FormRules = {
  positive_count: [{ type: 'number', min: 0, max: 10, message: '范围 0-10', trigger: 'change' }],
  boundary_count: [{ type: 'number', min: 0, max: 10, message: '范围 0-10', trigger: 'change' }],
  exception_count: [{ type: 'number', min: 0, max: 10, message: '范围 0-10', trigger: 'change' }],
  auth_count: [{ type: 'number', min: 0, max: 10, message: '范围 0-10', trigger: 'change' }],
}

function resetForm(): void {
  Object.assign(form, DEFAULT_AI_GENERATE_COUNTS)
  formRef.value?.clearValidate()
}

function validateTotalCount(): boolean {
  if (totalCount.value <= 0) {
    ElMessage.warning('请至少生成 1 条用例')
    return false
  }
  if (totalCount.value > 20) {
    ElMessage.warning('单次最多生成 20 条用例')
    return false
  }
  return true
}

async function handleSubmit(): Promise<void> {
  if (!props.endpoint) {
    return
  }

  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid || !validateTotalCount()) {
    return
  }

  generating.value = true
  try {
    const result = await generateAiTestCases(props.projectId, props.endpoint.id, {
      positive_count: form.positive_count,
      boundary_count: form.boundary_count,
      exception_count: form.exception_count,
      auth_count: form.auth_count,
    })

    const rejectedTip =
      result.rejected_count > 0 ? `，跳过 ${result.rejected_count} 条无效结果` : ''
    const partialTip =
      result.cases.length < result.requested_count
        ? `（请求 ${result.requested_count} 条，实际 ${result.cases.length} 条）`
        : ''
    ElMessage.success(
      `已生成 ${result.cases.length} 条 AI 候选用例${partialTip}${rejectedTip}`,
    )
    if (result.cases.length < result.requested_count) {
      ElMessage.warning(
        `仅生成 ${result.cases.length}/${result.requested_count} 条，请稍后重试或减少单次数量`,
      )
    }
    emit('generated', result)
    dialogVisible.value = false
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, 'AI 用例生成失败'))
  } finally {
    generating.value = false
  }
}

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      resetForm()
    }
  },
)
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    title="AI 生成测试用例"
    width="520px"
    destroy-on-close
    @closed="resetForm"
  >
    <div v-if="endpoint" class="endpoint-banner">
      <el-tag :type="methodTagType(endpoint.method)" size="small">
        {{ endpoint.method }}
      </el-tag>
      <span class="endpoint-text">{{ endpointLabel }}</span>
    </div>

    <el-form ref="formRef" :model="form" :rules="rules" label-width="120px" class="generate-form">
      <el-form-item label="正向用例" prop="positive_count">
        <el-input-number v-model="form.positive_count" :min="0" :max="10" />
        <span class="field-tip">合法输入，期望成功响应</span>
      </el-form-item>
      <el-form-item label="边界用例" prop="boundary_count">
        <el-input-number v-model="form.boundary_count" :min="0" :max="10" />
        <span class="field-tip">边界值与临界条件</span>
      </el-form-item>
      <el-form-item label="异常用例" prop="exception_count">
        <el-input-number v-model="form.exception_count" :min="0" :max="10" />
        <span class="field-tip">非法输入，期望错误响应</span>
      </el-form-item>
      <el-form-item label="鉴权用例" prop="auth_count">
        <el-input-number v-model="form.auth_count" :min="0" :max="10" />
        <span class="field-tip">缺失或无效凭证场景</span>
      </el-form-item>
    </el-form>

    <div class="total-line">
      合计生成：<strong>{{ totalCount }}</strong> 条（单次最多 20 条）
    </div>

    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="generating" @click="handleSubmit">
        开始生成
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.endpoint-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}

.endpoint-text {
  font-size: 13px;
  word-break: break-all;
}

.generate-form {
  margin-top: 4px;
}

.field-tip {
  margin-left: 12px;
  color: #909399;
  font-size: 12px;
}

.total-line {
  margin-top: 4px;
  color: #606266;
  font-size: 14px;
}
</style>
