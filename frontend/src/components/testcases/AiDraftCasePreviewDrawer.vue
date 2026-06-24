<script setup lang="ts">
import { computed } from 'vue'

import { formatResponseBody, type TestCase } from '@/api/testCases'

const props = defineProps<{
  visible: boolean
  testCase: TestCase | null
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
}>()

const drawerVisible = computed({
  get: () => props.visible,
  set: (value: boolean) => emit('update:visible', value),
})

const requestBodyText = computed(() => {
  const body = props.testCase?.request_json.body
  if (!body || body.type === 'none') {
    return ''
  }
  if (body.type === 'json') {
    return formatResponseBody(body.content)
  }
  return body.content
})

const assertionsText = computed(() => {
  if (!props.testCase) {
    return ''
  }
  return JSON.stringify(props.testCase.assertions_json, null, 2)
})

function methodTagType(method: string): 'success' | 'warning' | 'danger' | 'info' | '' {
  switch (method.toUpperCase()) {
    case 'GET':
      return 'success'
    case 'POST':
      return ''
    case 'PUT':
    case 'PATCH':
      return 'warning'
    case 'DELETE':
      return 'danger'
    default:
      return 'info'
  }
}
</script>

<template>
  <el-drawer
    v-model="drawerVisible"
    :title="testCase ? `预览 — ${testCase.name}` : '用例预览'"
    size="560px"
    destroy-on-close
  >
    <template v-if="testCase">
      <div class="preview-summary">
        <el-tag type="info" size="large">草稿</el-tag>
        <el-tag size="large">{{ testCase.priority }}</el-tag>
      </div>

      <section v-if="testCase.description" class="preview-section">
        <h4 class="section-title">描述</h4>
        <p class="text-line">{{ testCase.description }}</p>
      </section>

      <section class="preview-section">
        <h4 class="section-title">请求</h4>
        <p class="meta-line">
          <el-tag :type="methodTagType(testCase.request_json.method)" size="small">
            {{ testCase.request_json.method }}
          </el-tag>
          <span class="url-text">{{ testCase.request_json.url || '—' }}</span>
        </p>
        <div v-if="testCase.request_json.headers.length > 0" class="kv-block">
          <span class="meta-label">Headers</span>
          <el-table :data="testCase.request_json.headers" stripe size="small">
            <el-table-column prop="key" label="Key" width="140" />
            <el-table-column prop="value" label="Value" min-width="160" show-overflow-tooltip />
          </el-table>
        </div>
        <div v-if="testCase.request_json.query.length > 0" class="kv-block">
          <span class="meta-label">Query</span>
          <el-table :data="testCase.request_json.query" stripe size="small">
            <el-table-column prop="key" label="Key" width="140" />
            <el-table-column prop="value" label="Value" min-width="160" show-overflow-tooltip />
          </el-table>
        </div>
        <div v-if="requestBodyText" class="kv-block">
          <span class="meta-label">Body ({{ testCase.request_json.body.type }})</span>
          <el-input
            :model-value="requestBodyText"
            type="textarea"
            :rows="6"
            readonly
            class="json-viewer"
          />
        </div>
      </section>

      <section class="preview-section">
        <h4 class="section-title">断言</h4>
        <div class="meta-grid">
          <div>
            <span class="meta-label">Status Code</span>
            <el-tag>{{ testCase.assertions_json.status_code }}</el-tag>
          </div>
          <div>
            <span class="meta-label">最大耗时</span>
            <span>{{ testCase.assertions_json.max_response_time_ms }} ms</span>
          </div>
        </div>
        <el-input
          :model-value="assertionsText"
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
.preview-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.preview-section {
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

.meta-line {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
}

.url-text {
  word-break: break-all;
  font-size: 13px;
}

.kv-block {
  margin-bottom: 12px;
}

.meta-grid {
  display: flex;
  gap: 24px;
  margin-bottom: 10px;
}

.meta-label {
  display: block;
  margin-bottom: 4px;
  color: #909399;
  font-size: 12px;
}

.json-viewer {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
</style>
