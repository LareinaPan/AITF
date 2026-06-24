<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import type { BodyType, HttpMethod, KeyValueItem, TestCaseRequestJson } from '@/api/testCases'

interface KeyValueRow extends KeyValueItem {
  _rowId: string
}

const model = defineModel<TestCaseRequestJson>({ required: true })

const activeTab = ref('headers')

const httpMethods: HttpMethod[] = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']
const bodyTypes: Array<{ label: string; value: BodyType }> = [
  { label: 'None', value: 'none' },
  { label: 'JSON', value: 'json' },
  { label: 'Raw', value: 'raw' },
  { label: 'Form', value: 'form' },
]

const headerRows = ref<KeyValueRow[]>([])
const queryRows = ref<KeyValueRow[]>([])

function createRowId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function toRows(items: KeyValueItem[]): KeyValueRow[] {
  return items.map((item) => ({
    ...item,
    _rowId: createRowId(),
  }))
}

function rowsToItems(rows: KeyValueRow[]): KeyValueItem[] {
  return rows.map(({ key, value }) => ({ key, value }))
}

function syncRowsFromModel(): void {
  headerRows.value = toRows(model.value.headers ?? [])
  queryRows.value = toRows(model.value.query ?? [])
}

function patchModel(patch: Partial<TestCaseRequestJson>): void {
  model.value = {
    ...model.value,
    ...patch,
    headers: rowsToItems(headerRows.value),
    query: rowsToItems(queryRows.value),
  }
}

function getCurrentRequestJson(): TestCaseRequestJson {
  return {
    ...model.value,
    headers: rowsToItems(headerRows.value),
    query: rowsToItems(queryRows.value),
  }
}

function updateMethod(method: HttpMethod): void {
  patchModel({ method })
}

function updateUrl(url: string): void {
  patchModel({ url })
}

function updateBodyType(type: BodyType): void {
  patchModel({ body: { ...model.value.body, type } })
}

function updateBodyContent(content: string): void {
  patchModel({ body: { ...model.value.body, content } })
}

function addHeaderRow(): void {
  headerRows.value.push({ _rowId: createRowId(), key: '', value: '' })
}

function removeHeaderRow(rowId: string): void {
  headerRows.value = headerRows.value.filter((row) => row._rowId !== rowId)
}

function addQueryRow(): void {
  queryRows.value.push({ _rowId: createRowId(), key: '', value: '' })
}

function removeQueryRow(rowId: string): void {
  queryRows.value = queryRows.value.filter((row) => row._rowId !== rowId)
}

const bodyPlaceholder = computed(() => {
  switch (model.value.body.type) {
    case 'json':
      return '{\n  "username": "test"\n}'
    case 'form':
      return 'key1=value1&key2=value2'
    case 'raw':
      return 'plain text body'
    default:
      return ''
  }
})

defineExpose({ getCurrentRequestJson })

onMounted(syncRowsFromModel)
</script>

<template>
  <div class="request-editor">
    <div class="request-line">
      <el-select :model-value="model.method" class="method-select" @update:model-value="updateMethod">
        <el-option v-for="item in httpMethods" :key="item" :label="item" :value="item" />
      </el-select>
      <el-input
        :model-value="model.url"
        placeholder="如 {{base_url}}/api/users"
        @update:model-value="updateUrl"
      />
    </div>

    <el-tabs v-model="activeTab" class="request-tabs">
      <el-tab-pane label="Headers" name="headers">
        <div class="tab-toolbar">
          <el-button size="small" @click="addHeaderRow">添加 Header</el-button>
        </div>
        <el-table :data="headerRows" stripe empty-text="暂无 Header">
          <el-table-column label="Key" min-width="180">
            <template #default="{ row }">
              <el-input v-model="row.key" placeholder="Content-Type" />
            </template>
          </el-table-column>
          <el-table-column label="Value" min-width="280">
            <template #default="{ row }">
              <el-input v-model="row.value" placeholder="application/json" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" align="center">
            <template #default="{ row }">
              <el-button link type="danger" @click="removeHeaderRow(row._rowId)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="Query" name="query">
        <div class="tab-toolbar">
          <el-button size="small" @click="addQueryRow">添加参数</el-button>
        </div>
        <el-table :data="queryRows" stripe empty-text="暂无 Query 参数">
          <el-table-column label="Key" min-width="180">
            <template #default="{ row }">
              <el-input v-model="row.key" placeholder="page" />
            </template>
          </el-table-column>
          <el-table-column label="Value" min-width="280">
            <template #default="{ row }">
              <el-input v-model="row.value" placeholder="1" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" align="center">
            <template #default="{ row }">
              <el-button link type="danger" @click="removeQueryRow(row._rowId)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="Body" name="body">
        <div class="body-toolbar">
          <el-radio-group :model-value="model.body.type" @update:model-value="updateBodyType">
            <el-radio-button v-for="item in bodyTypes" :key="item.value" :value="item.value">
              {{ item.label }}
            </el-radio-button>
          </el-radio-group>
        </div>
        <el-input
          v-if="model.body.type !== 'none'"
          :model-value="model.body.content"
          type="textarea"
          :rows="10"
          :placeholder="bodyPlaceholder"
          class="body-editor"
          @update:model-value="updateBodyContent"
        />
        <el-empty v-else description="当前请求无 Body" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.request-editor {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.request-line {
  display: flex;
  gap: 8px;
}

.method-select {
  width: 120px;
  flex-shrink: 0;
}

.request-tabs {
  margin-top: 4px;
}

.tab-toolbar,
.body-toolbar {
  margin-bottom: 12px;
}

.body-editor {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
</style>
