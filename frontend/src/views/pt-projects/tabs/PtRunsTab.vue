<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import type { PtProject } from '@/api/pt-projects'
import {
  fetchPtRuns,
  ptRunDetailPath,
  runStatusLabel,
  runStatusTagType,
  stopReasonLabel,
  type PtRunListItem,
  type PtRunStatus,
} from '@/api/pt-runs'
import { getApiErrorMessage } from '@/api/request'
import AsyncState from '@/components/common/AsyncState.vue'
import { formatBeijingTime } from '@/utils/datetime'

const props = defineProps<{
  project: PtProject
}>()

const router = useRouter()

const loading = ref(false)
const loadError = ref<string | null>(null)
const runs = ref<PtRunListItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const statusFilter = ref<PtRunStatus | ''>('')

const statusOptions: Array<{ value: PtRunStatus | ''; label: string }> = [
  { value: '', label: '全部状态' },
  { value: 'running', label: '运行中' },
  { value: 'completed', label: '已完成' },
  { value: 'cancelled', label: '已取消' },
  { value: 'failed', label: '失败' },
]

async function loadRuns(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    const response = await fetchPtRuns(props.project.id, {
      page: page.value,
      page_size: pageSize.value,
      status: statusFilter.value || undefined,
    })
    runs.value = response.items
    total.value = response.total
  } catch (error) {
    loadError.value = getApiErrorMessage(error, '加载运行记录失败')
  } finally {
    loading.value = false
  }
}

function handleStatusFilterChange(): void {
  page.value = 1
  void loadRuns()
}

function handlePageChange(nextPage: number): void {
  page.value = nextPage
  void loadRuns()
}

function handlePageSizeChange(nextSize: number): void {
  pageSize.value = nextSize
  page.value = 1
  void loadRuns()
}

function openRunDetail(runId: string): void {
  void router.push(ptRunDetailPath(props.project.id, runId))
}

onMounted(loadRuns)
watch(
  () => props.project.id,
  () => {
    page.value = 1
    statusFilter.value = ''
    void loadRuns()
  },
)
</script>

<template>
  <div class="pt-runs-tab">
    <AsyncState :loading="loading" :error="loadError" @retry="loadRuns">
      <div class="tab-toolbar">
        <p class="tab-desc">按开始时间倒序展示压测运行记录</p>
        <el-select
          v-model="statusFilter"
          class="status-filter"
          placeholder="全部状态"
          @change="handleStatusFilterChange"
        >
          <el-option
            v-for="option in statusOptions"
            :key="option.value || 'all'"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
      </div>

      <el-table
        v-loading="loading"
        :data="runs"
        stripe
        empty-text="暂无运行记录，可在压测详情中点击「运行」发起压测"
      >
        <el-table-column prop="scenario_name_snapshot" label="压测场景" min-width="160" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="runStatusTagType(row.status)" size="small">
              {{ runStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="停止原因" min-width="120">
          <template #default="{ row }">
            {{ stopReasonLabel(row.stop_reason) }}
          </template>
        </el-table-column>
        <el-table-column label="开始时间" min-width="170">
          <template #default="{ row }">
            {{ formatBeijingTime(row.started_at) }}
          </template>
        </el-table-column>
        <el-table-column label="结束时间" min-width="170">
          <template #default="{ row }">
            {{ row.ended_at ? formatBeijingTime(row.ended_at) : '—' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openRunDetail(row.id)">查看详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="total > 0" class="pagination-bar">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />
      </div>
    </AsyncState>
  </div>
</template>

<style scoped>
.pt-runs-tab {
  margin-top: 8px;
}

.tab-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.tab-desc {
  margin: 0;
  color: #909399;
  font-size: 14px;
}

.status-filter {
  width: 140px;
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
