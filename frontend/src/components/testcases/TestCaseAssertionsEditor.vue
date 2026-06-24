<script setup lang="ts">
import { onMounted, ref } from 'vue'

import {
  bodyRulesToRows,
  buildAssertionsPayloadFromForm,
  type BodyRuleRow,
  type BodyRuleType,
  type TestCaseAssertionsJson,
} from '@/api/testCases'

const model = defineModel<TestCaseAssertionsJson>({ required: true })

const statusCode = ref(200)
const maxResponseTimeMs = ref(3000)
const bodyRuleRows = ref<BodyRuleRow[]>([])

const ruleTypeOptions: Array<{ label: string; value: BodyRuleType }> = [
  { label: '包含文本 (contains)', value: 'contains' },
  { label: 'JSONPath 等于 (eq)', value: 'json_path' },
]

function createRowId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function syncFromModel(): void {
  statusCode.value = model.value.status_code
  maxResponseTimeMs.value = model.value.max_response_time_ms
  bodyRuleRows.value = bodyRulesToRows(model.value.body_rules ?? [])
}

function getCurrentAssertionsJson(): TestCaseAssertionsJson {
  return buildAssertionsPayloadFromForm(
    statusCode.value,
    maxResponseTimeMs.value,
    bodyRuleRows.value,
  )
}

function addBodyRuleRow(): void {
  bodyRuleRows.value.push({
    _rowId: createRowId(),
    type: 'contains',
    value: '',
    path: '',
    expected: '',
  })
}

function removeBodyRuleRow(rowId: string): void {
  bodyRuleRows.value = bodyRuleRows.value.filter((row) => row._rowId !== rowId)
}

defineExpose({ getCurrentAssertionsJson })

onMounted(syncFromModel)
</script>

<template>
  <div class="assertions-editor">
    <el-row :gutter="16">
      <el-col :span="12">
        <el-form-item label="期望 Status Code">
          <el-input-number
            v-model="statusCode"
            :min="100"
            :max="599"
            :step="1"
            controls-position="right"
            style="width: 100%"
          />
        </el-form-item>
      </el-col>
      <el-col :span="12">
        <el-form-item label="最大响应时间 (ms)">
          <el-input-number
            v-model="maxResponseTimeMs"
            :min="0"
            :max="300000"
            :step="100"
            controls-position="right"
            style="width: 100%"
          />
        </el-form-item>
      </el-col>
    </el-row>

    <div class="rules-header">
      <span class="rules-title">Body 断言规则</span>
      <el-button size="small" @click="addBodyRuleRow">添加规则</el-button>
    </div>

    <el-table :data="bodyRuleRows" stripe empty-text="暂无 Body 规则，点击「添加规则」">
      <el-table-column label="类型" width="200">
        <template #default="{ row }">
          <el-select v-model="row.type" style="width: 100%">
            <el-option
              v-for="item in ruleTypeOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="规则配置" min-width="360">
        <template #default="{ row }">
          <el-input
            v-if="row.type === 'contains'"
            v-model="row.value"
            placeholder="响应体应包含的文本，如 success"
          />
          <div v-else class="json-path-fields">
            <el-input v-model="row.path" placeholder="JSONPath，如 $.code" />
            <el-input v-model="row.expected" placeholder="期望值，如 0" />
          </div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="80" align="center">
        <template #default="{ row }">
          <el-button link type="danger" @click="removeBodyRuleRow(row._rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.assertions-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rules-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 8px 0 12px;
}

.rules-title {
  font-size: 14px;
  font-weight: 600;
}

.json-path-fields {
  display: flex;
  gap: 8px;
}
</style>
