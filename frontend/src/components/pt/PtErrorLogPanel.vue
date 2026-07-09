<script setup lang="ts">
import { computed, ref } from 'vue'

import {
  fetchPtRunErrors,
  type PtRunErrorLog,
} from '@/api/pt-runs'
import { getApiErrorMessage } from '@/api/request'
import { formatBeijingTime } from '@/utils/datetime'

const props = defineProps<{
  projectId: string
  runId: string
  errors: PtRunErrorLog[]
}>()

const drawerVisible = ref(false)
const drawerLoading = ref(false)
const drawerError = ref<string | null>(null)
const allErrors = ref<PtRunErrorLog[]>([])
const allTotal = ref(0)
const allPage = ref(1)
const allPageSize = ref(20)

const latestErrors = computed(() => props.errors.slice(0, 10))

async function loadAllErrors(): Promise<void> {
  drawerLoading.value = true
  drawerError.value = null
  try {
    const response = await fetchPtRunErrors(props.projectId, props.runId, {
      page: allPage.value,
      page_size: allPageSize.value,
    })
    allErrors.value = response.items
    allTotal.value = response.total ?? 0
  } catch (error) {
    drawerError.value = getApiErrorMessage(error, '加载全部错误日志失败')
  } finally {
    drawerLoading.value = false
  }
}

async function openDrawer(): Promise<void> {
  drawerVisible.value = true
  allPage.value = 1
  await loadAllErrors()
}

async function handlePageChange(page: number): Promise<void> {
  allPage.value = page
  await loadAllErrors()
}

async function handlePageSizeChange(size: number): Promise<void> {
  allPageSize.value = size
  allPage.value = 1
  await loadAllErrors()
}
</script>

<template>
  <div class="pt-error-log-panel">
    <div class="panel-header">
      <h3 class="panel-title">错误日志</h3>
      <el-button link type="primary" @click="openDrawer">查看全部</el-button>
    </div>

    <el-empty v-if="latestErrors.length === 0" description="暂无错误日志" />
    <el-table v-else :data="latestErrors" stripe size="small">
      <el-table-column label="时间" min-width="160">
        <template #default="{ row }">
          {{ formatBeijingTime(row.occurred_at) }}
        </template>
      </el-table-column>
      <el-table-column prop="sampler_name" label="接口" min-width="140" show-overflow-tooltip />
      <el-table-column label="状态码" width="90">
        <template #default="{ row }">
          {{ row.status_code ?? '—' }}
        </template>
      </el-table-column>
      <el-table-column prop="error_type" label="类型" width="120" />
      <el-table-column prop="message" label="摘要" min-width="220" show-overflow-tooltip />
    </el-table>

    <el-drawer v-model="drawerVisible" title="全部错误日志" size="720px">
      <el-alert
        v-if="drawerError"
        :title="drawerError"
        type="error"
        show-icon
        :closable="false"
        class="drawer-alert"
      />
      <el-table v-loading="drawerLoading" :data="allErrors" stripe>
        <el-table-column label="时间" min-width="160">
          <template #default="{ row }">
            {{ formatBeijingTime(row.occurred_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="sampler_name" label="接口" min-width="140" show-overflow-tooltip />
        <el-table-column label="状态码" width="90">
          <template #default="{ row }">
            {{ row.status_code ?? '—' }}
          </template>
        </el-table-column>
        <el-table-column prop="error_type" label="类型" width="120" />
        <el-table-column prop="message" label="摘要" min-width="220" show-overflow-tooltip />
      </el-table>
      <div v-if="allTotal > 0" class="drawer-pagination">
        <el-pagination
          v-model:current-page="allPage"
          v-model:page-size="allPageSize"
          :total="allTotal"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.pt-error-log-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.panel-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.drawer-alert {
  margin-bottom: 12px;
}

.drawer-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
