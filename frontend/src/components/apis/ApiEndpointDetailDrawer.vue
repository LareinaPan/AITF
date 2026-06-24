<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import {
  fetchApiEndpoint,
  formatJson,
  methodTagType,
  type ApiEndpoint,
} from '@/api/apiEndpoints'
import { getApiErrorMessage } from '@/api/request'

const props = defineProps<{
  visible: boolean
  projectId: string
  endpointId: string | null
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
}>()

const loading = ref(false)
const endpoint = ref<ApiEndpoint | null>(null)

const drawerVisible = computed({
  get: () => props.visible,
  set: (value: boolean) => emit('update:visible', value),
})

const parametersText = computed(() => formatJson(endpoint.value?.parameters_json ?? []))
const requestBodyText = computed(() => formatJson(endpoint.value?.request_body_json))
const responsesText = computed(() => formatJson(endpoint.value?.responses_json ?? {}))

async function loadEndpoint(): Promise<void> {
  if (!props.endpointId) {
    endpoint.value = null
    return
  }

  loading.value = true
  try {
    endpoint.value = await fetchApiEndpoint(props.projectId, props.endpointId)
  } catch (error) {
    endpoint.value = null
    ElMessage.error(getApiErrorMessage(error, '加载接口详情失败'))
    drawerVisible.value = false
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.visible, props.endpointId] as const,
  ([visible, endpointId]) => {
    if (visible && endpointId) {
      loadEndpoint()
    }
    if (!visible) {
      endpoint.value = null
    }
  },
)
</script>

<template>
  <el-drawer
    v-model="drawerVisible"
    :title="endpoint ? `${endpoint.method} ${endpoint.path}` : '接口详情'"
    size="560px"
    destroy-on-close
  >
    <div v-if="loading" v-loading="true" class="drawer-loading" />

    <template v-else-if="endpoint">
      <div class="endpoint-summary">
        <el-tag :type="methodTagType(endpoint.method)" size="large">
          {{ endpoint.method }}
        </el-tag>
        <span class="path-text">{{ endpoint.path }}</span>
      </div>

      <section class="detail-section">
        <h4 class="section-title">摘要</h4>
        <p class="text-line">{{ endpoint.summary || '—' }}</p>
      </section>

      <section v-if="endpoint.description" class="detail-section">
        <h4 class="section-title">描述</h4>
        <p class="text-line">{{ endpoint.description }}</p>
      </section>

      <section class="detail-section">
        <h4 class="section-title">Parameters</h4>
        <el-input
          :model-value="parametersText"
          type="textarea"
          :rows="6"
          readonly
          class="json-viewer"
        />
      </section>

      <section class="detail-section">
        <h4 class="section-title">Request Body</h4>
        <el-input
          :model-value="requestBodyText || '—'"
          type="textarea"
          :rows="6"
          readonly
          class="json-viewer"
        />
      </section>

      <section class="detail-section">
        <h4 class="section-title">Responses</h4>
        <el-input
          :model-value="responsesText"
          type="textarea"
          :rows="8"
          readonly
          class="json-viewer"
        />
      </section>
    </template>
  </el-drawer>
</template>

<style scoped>
.drawer-loading {
  min-height: 200px;
}

.endpoint-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 18px;
}

.path-text {
  word-break: break-all;
  font-size: 15px;
  font-weight: 600;
}

.detail-section {
  margin-bottom: 18px;
}

.section-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
}

.text-line {
  margin: 0;
  color: #606266;
  line-height: 1.6;
}

.json-viewer {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
</style>
