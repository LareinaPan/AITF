<script setup lang="ts">
import { computed } from 'vue'

import { formatResponseBody, type TestCaseRunResult } from '@/api/testCases'

const props = defineProps<{
  visible: boolean
  result: TestCaseRunResult | null
  running: boolean
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
}>()

const drawerVisible = computed({
  get: () => props.visible,
  set: (value: boolean) => emit('update:visible', value),
})

const formattedBody = computed(() =>
  props.result?.response ? formatResponseBody(props.result.response.body) : '',
)

function checkTagType(passed: boolean): 'success' | 'danger' {
  return passed ? 'success' : 'danger'
}
</script>

<template>
  <el-drawer
    v-model="drawerVisible"
    :title="result ? `执行结果 — ${result.case_name}` : '执行结果'"
    size="520px"
    destroy-on-close
  >
    <div v-if="running" v-loading="true" class="drawer-loading" />

    <template v-else-if="result">
      <div class="result-summary">
        <el-tag :type="result.passed ? 'success' : 'danger'" size="large">
          {{ result.passed ? '通过' : '失败' }}
        </el-tag>
        <span class="env-label">环境：{{ result.environment_name }}</span>
      </div>

      <el-alert
        v-if="result.error"
        :title="result.error"
        type="error"
        show-icon
        :closable="false"
        class="result-alert"
      />

      <section class="result-section">
        <h4 class="section-title">请求</h4>
        <p class="meta-line">
          <el-tag size="small">{{ result.prepared_request.method }}</el-tag>
          <span class="url-text">{{ result.prepared_request.url }}</span>
        </p>
      </section>

      <section v-if="result.response" class="result-section">
        <h4 class="section-title">响应</h4>
        <div class="meta-grid">
          <div>
            <span class="meta-label">Status Code</span>
            <el-tag :type="result.response.status_code < 400 ? 'success' : 'danger'">
              {{ result.response.status_code }}
            </el-tag>
          </div>
          <div>
            <span class="meta-label">耗时</span>
            <span>{{ result.response.elapsed_ms.toFixed(2) }} ms</span>
          </div>
        </div>
        <el-input
          :model-value="formattedBody"
          type="textarea"
          :rows="8"
          readonly
          class="body-viewer"
        />
      </section>

      <section v-if="result.assertions" class="result-section">
        <h4 class="section-title">断言明细</h4>
        <el-table :data="result.assertions.checks" stripe size="small">
          <el-table-column label="结果" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="checkTagType(row.passed)" size="small">
                {{ row.passed ? '通过' : '失败' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="项" width="140" />
          <el-table-column prop="message" label="说明" min-width="200" show-overflow-tooltip />
        </el-table>
      </section>
    </template>
  </el-drawer>
</template>

<style scoped>
.drawer-loading {
  min-height: 200px;
}

.result-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.env-label {
  color: #606266;
  font-size: 14px;
}

.result-alert {
  margin-bottom: 16px;
}

.result-section {
  margin-bottom: 20px;
}

.section-title {
  margin: 0 0 10px;
  font-size: 15px;
  font-weight: 600;
}

.meta-line {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}

.url-text {
  word-break: break-all;
  font-size: 13px;
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

.body-viewer {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
</style>
