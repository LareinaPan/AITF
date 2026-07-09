<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { UploadInstance, UploadProps, UploadRawFile } from 'element-plus'
import { ElMessage } from 'element-plus'
import { isAxiosError } from 'axios'

import { fetchPtScenario, type PtScenario } from '@/api/pt-scenarios'
import { fetchPtScript, uploadPtScript, type PtScript } from '@/api/pt-scripts'
import { ptRunDetailPath, resolvePtRunLaunchTarget } from '@/api/pt-runs'
import { getApiErrorMessage } from '@/api/request'
import { FormUploadError } from '@/api/form-upload'
import AsyncState from '@/components/common/AsyncState.vue'
import PtLoadConfigForm from '@/components/pt/PtLoadConfigForm.vue'
import { formatBeijingTime } from '@/utils/datetime'
import {
  parseStatusLabel,
  parseStatusTagType,
} from '@/api/pt-scenarios'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const loadError = ref<string | null>(null)
const uploading = ref(false)
const running = ref(false)
const scenario = ref<PtScenario | null>(null)
const script = ref<PtScript | null>(null)
const uploadRef = ref<UploadInstance>()

const projectId = computed(() => route.params.id as string)
const scenarioId = computed(() => route.params.scenarioId as string)

const parseStatus = computed(() => script.value?.parse_status ?? 'pending')

async function loadPageData(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    const [scenarioData, scriptData] = await Promise.all([
      fetchPtScenario(projectId.value, scenarioId.value),
      fetchPtScript(projectId.value, scenarioId.value),
    ])
    scenario.value = scenarioData
    script.value = scriptData
  } catch (error) {
    loadError.value = getApiErrorMessage(error, '加载脚本配置失败')
  } finally {
    loading.value = false
  }
}

const beforeUpload: UploadProps['beforeUpload'] = (rawFile: UploadRawFile) => {
  if (!rawFile.name.toLowerCase().endsWith('.jmx')) {
    ElMessage.error('仅支持上传 .jmx 文件')
    return false
  }
  return true
}

const handleUpload: UploadProps['httpRequest'] = async (options) => {
  const rawFile = options.file as UploadRawFile
  uploading.value = true
  try {
    script.value = await uploadPtScript(projectId.value, scenarioId.value, rawFile)
    scenario.value = await fetchPtScenario(projectId.value, scenarioId.value)
    if (script.value.parse_status === 'success') {
      ElMessage.success('JMX 解析成功')
    } else {
      ElMessage.warning(script.value.parse_error || 'JMX 解析失败')
    }
    options.onSuccess?.(script.value)
  } catch (error) {
    const message =
      error instanceof FormUploadError
        ? error.message
        : getApiErrorMessage(error, 'JMX 上传失败')
    ElMessage.error(message)
    options.onError?.(error as Error)
  } finally {
    uploading.value = false
    uploadRef.value?.clearFiles()
  }
}

function goBack(): void {
  router.push({ name: 'pt-project-scenarios', params: { id: projectId.value } })
}

function handleConfigSaved(updated: PtScript): void {
  script.value = updated
}

async function handleRun(): Promise<void> {
  if (!script.value || script.value.parse_status !== 'success') {
    ElMessage.warning('请先上传并成功解析 JMX 脚本')
    return
  }

  running.value = true
  try {
    const target = await resolvePtRunLaunchTarget(projectId.value, scenarioId.value)
    await router.push(ptRunDetailPath(projectId.value, target.runId))
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
    running.value = false
  }
}

onMounted(loadPageData)
watch([projectId, scenarioId], loadPageData)
</script>

<template>
  <AsyncState :loading="loading" :error="loadError" @retry="loadPageData">
    <div class="pt-script-page">
      <el-page-header @back="goBack">
        <template #content>
          <div class="page-header-content">
            <span class="page-title">{{ scenario?.name ?? '脚本配置' }}</span>
            <el-button
              type="success"
              :loading="running"
              :disabled="parseStatus !== 'success'"
              @click="handleRun"
            >
              运行压测
            </el-button>
          </div>
        </template>
      </el-page-header>

      <el-card shadow="never" class="section-card">
        <template #header>
          <div class="card-header">
            <span>JMeter 脚本</span>
            <el-tag :type="parseStatusTagType(parseStatus)" size="small">
              {{ parseStatusLabel(parseStatus) }}
            </el-tag>
          </div>
        </template>

        <div class="upload-row">
          <el-upload
            ref="uploadRef"
            :show-file-list="false"
            :before-upload="beforeUpload"
            :http-request="handleUpload"
            accept=".jmx"
          >
            <el-button type="primary" :loading="uploading">
              {{ script?.filename ? '重新上传 .jmx' : '上传 .jmx' }}
            </el-button>
          </el-upload>
          <span class="upload-hint">单文件 ≤ 10 MB；上传后将自动解析 HTTP 接口（只读展示）</span>
        </div>

        <el-descriptions v-if="script" :column="2" border class="meta-block">
          <el-descriptions-item label="文件名">
            {{ script.filename || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="文件大小">
            {{ script.file_size ? `${script.file_size} B` : '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="Thread Group 数">
            {{ script.thread_group_count }}
          </el-descriptions-item>
          <el-descriptions-item label="HTTP 接口数">
            {{ script.sampler_count }}
          </el-descriptions-item>
          <el-descriptions-item label="上传时间">
            {{ script.uploaded_at ? formatBeijingTime(script.uploaded_at) : '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="解析错误">
            {{ script.parse_error || '—' }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card v-if="script?.parsed_plan?.samplers?.length" shadow="never" class="section-card">
        <template #header>
          <span>解析出的 HTTP 接口（只读）</span>
        </template>

        <el-table :data="script.parsed_plan.samplers" stripe>
          <el-table-column prop="name" label="Sampler 名称" min-width="160" />
          <el-table-column prop="method" label="Method" width="100" />
          <el-table-column prop="url" label="URL / Path" min-width="260" show-overflow-tooltip />
          <el-table-column label="变量" width="90">
            <template #default="{ row }">
              <el-tag v-if="row.has_variables" type="warning" size="small">含变量</el-tag>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column prop="thread_group_name" label="Thread Group" min-width="140" />
          <el-table-column label="Headers" min-width="180">
            <template #default="{ row }">
              <span v-if="row.headers.length">
                {{ row.headers.map((item) => item.name).join(', ') }}
              </span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
        </el-table>

        <el-alert
          v-if="script.parsed_plan.parse_warnings.length"
          class="warnings"
          type="warning"
          :closable="false"
          show-icon
          title="解析提示"
        >
          <ul class="warning-list">
            <li v-for="warning in script.parsed_plan.parse_warnings" :key="warning">
              {{ warning }}
            </li>
          </ul>
        </el-alert>
      </el-card>

      <el-empty
        v-else-if="script && script.parse_status !== 'pending'"
        description="未解析出 HTTP 接口"
      />

      <PtLoadConfigForm
        v-if="script"
        :project-id="projectId"
        :scenario-id="scenarioId"
        :script="script"
        @saved="handleConfigSaved"
      />
    </div>
  </AsyncState>
</template>

<style scoped>
.pt-script-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-title {
  font-size: 18px;
  font-weight: 600;
}

.page-header-content {
  display: flex;
  align-items: center;
  gap: 16px;
}

.section-card {
  margin-top: 4px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.upload-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.upload-hint {
  color: #909399;
  font-size: 13px;
}

.meta-block {
  margin-top: 8px;
}

.warnings {
  margin-top: 16px;
}

.warning-list {
  margin: 0;
  padding-left: 18px;
}

.muted {
  color: #c0c4cc;
}
</style>
