<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'

import {
  updatePtScriptConfig,
  type ParsedSampler,
  type PtScript,
  type PtScriptConfigPayload,
} from '@/api/pt-scripts'
import { getApiErrorMessage } from '@/api/request'

const props = defineProps<{
  projectId: string
  scenarioId: string
  script: PtScript
}>()

const emit = defineEmits<{
  saved: [script: PtScript]
}>()

const formRef = ref<FormInstance>()
const saving = ref(false)

const form = reactive({
  max_concurrency: 10,
  ramp_up_seconds: 0,
  stop_mode: 'duration' as 'request_limit' | 'duration',
  duration_seconds: 60,
  default_max_requests: 1000,
})

const samplerLimits = ref<Record<string, number>>({})

const samplers = computed<ParsedSampler[]>(() => props.script.parsed_plan?.samplers ?? [])

const rules = computed<FormRules>(() => ({
  max_concurrency: [
    { required: true, message: '请输入最大并发数', trigger: 'blur' },
    {
      type: 'number',
      min: 1,
      max: 1000,
      message: '并发数范围为 1–1000',
      trigger: 'blur',
    },
  ],
  ramp_up_seconds: [
    { required: true, message: '请输入 Ramp-up 时长', trigger: 'blur' },
    { type: 'number', min: 0, message: 'Ramp-up 不能为负数', trigger: 'blur' },
  ],
  duration_seconds: form.stop_mode === 'duration'
    ? [
        { required: true, message: '请输入运行时长', trigger: 'blur' },
        {
          type: 'number',
          min: 10,
          max: 86400,
          message: '运行时长范围为 10–86400 秒',
          trigger: 'blur',
        },
      ]
    : [],
  default_max_requests: form.stop_mode === 'request_limit'
    ? [
        { required: true, message: '请输入默认请求上限', trigger: 'blur' },
        { type: 'number', min: 1, message: '请求上限至少为 1', trigger: 'blur' },
      ]
    : [],
}))

function syncFromScript(script: PtScript): void {
  form.max_concurrency = script.max_concurrency
  form.ramp_up_seconds = script.ramp_up_seconds
  form.stop_mode = script.stop_mode
  form.duration_seconds = script.duration_seconds ?? 60
  form.default_max_requests = script.default_max_requests

  const limits: Record<string, number> = {}
  for (const sampler of script.parsed_plan?.samplers ?? []) {
    limits[sampler.key] =
      script.sampler_limits?.[sampler.key] ?? script.default_max_requests
  }
  samplerLimits.value = limits
}

function applyDefaultToAllSamplers(): void {
  for (const sampler of samplers.value) {
    samplerLimits.value[sampler.key] = form.default_max_requests
  }
}

function buildPayload(): PtScriptConfigPayload {
  const payload: PtScriptConfigPayload = {
    max_concurrency: form.max_concurrency,
    ramp_up_seconds: form.ramp_up_seconds,
    stop_mode: form.stop_mode,
  }
  if (form.stop_mode === 'duration') {
    payload.duration_seconds = form.duration_seconds
    payload.sampler_limits = null
  } else {
    payload.default_max_requests = form.default_max_requests
    const limits: Record<string, number> = {}
    for (const sampler of samplers.value) {
      limits[sampler.key] = samplerLimits.value[sampler.key] ?? form.default_max_requests
    }
    const hasOverride = samplers.value.some(
      (sampler) => limits[sampler.key] !== form.default_max_requests,
    )
    payload.sampler_limits = hasOverride ? limits : null
  }
  return payload
}

async function handleSave(): Promise<void> {
  if (!formRef.value) {
    return
  }
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) {
    return
  }

  saving.value = true
  try {
    const updated = await updatePtScriptConfig(
      props.projectId,
      props.scenarioId,
      buildPayload(),
    )
    emit('saved', updated)
    ElMessage.success('压测参数已保存')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '保存压测参数失败'))
  } finally {
    saving.value = false
  }
}

watch(
  () => props.script,
  (script) => syncFromScript(script),
  { immediate: true },
)
</script>

<template>
  <el-card shadow="never" class="config-card">
    <template #header>
      <div class="card-header">
        <span>压测参数配置</span>
        <el-button type="primary" :loading="saving" @click="handleSave">保存配置</el-button>
      </div>
    </template>

    <el-form ref="formRef" :model="form" :rules="rules" label-width="140px">
      <el-form-item label="最大并发数" prop="max_concurrency">
        <el-input-number v-model="form.max_concurrency" :min="1" :max="1000" />
        <span class="field-hint">虚拟用户上限，范围 1–1000</span>
      </el-form-item>

      <el-form-item label="Ramp-up（秒）" prop="ramp_up_seconds">
        <el-input-number v-model="form.ramp_up_seconds" :min="0" :max="86400" />
        <span class="field-hint">从 0 线性加压到最大并发的秒数</span>
      </el-form-item>

      <el-form-item label="停止条件">
        <el-radio-group v-model="form.stop_mode">
          <el-radio value="duration">按运行时长</el-radio>
          <el-radio value="request_limit">按接口请求数</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item
        v-if="form.stop_mode === 'duration'"
        label="运行时长（秒）"
        prop="duration_seconds"
      >
        <el-input-number v-model="form.duration_seconds" :min="10" :max="86400" />
        <span class="field-hint">达到指定秒数后停止，范围 10–86400</span>
      </el-form-item>

      <template v-else>
        <el-form-item label="默认请求上限" prop="default_max_requests">
          <el-input-number v-model="form.default_max_requests" :min="1" :max="10000000" />
          <span class="field-hint">未单独配置的接口将使用此上限</span>
        </el-form-item>

        <el-form-item v-if="samplers.length" label="单接口上限">
          <div class="sampler-limits">
            <div class="sampler-limits-toolbar">
              <el-button size="small" @click="applyDefaultToAllSamplers">
                全部设为默认值
              </el-button>
            </div>
            <el-table :data="samplers" stripe size="small">
              <el-table-column prop="name" label="Sampler" min-width="160" />
              <el-table-column prop="method" label="Method" width="90" />
              <el-table-column prop="url" label="URL" min-width="200" show-overflow-tooltip />
              <el-table-column label="最大请求数" width="160">
                <template #default="{ row }">
                  <el-input-number
                    v-model="samplerLimits[row.key]"
                    :min="1"
                    :max="10000000"
                    size="small"
                  />
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-form-item>
      </template>
    </el-form>
  </el-card>
</template>

<style scoped>
.config-card {
  margin-top: 4px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.field-hint {
  margin-left: 12px;
  color: #909399;
  font-size: 13px;
}

.sampler-limits {
  width: 100%;
}

.sampler-limits-toolbar {
  margin-bottom: 8px;
}
</style>
