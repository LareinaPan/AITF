<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { fetchPtProjectStats, type PtProject, type PtProjectStats } from '@/api/pt-projects'
import { getApiErrorMessage } from '@/api/request'
import AsyncState from '@/components/common/AsyncState.vue'
import { formatBeijingTime } from '@/utils/datetime'

const props = defineProps<{
  project: PtProject
}>()

const router = useRouter()

const loading = ref(false)
const loadError = ref<string | null>(null)
const stats = ref<PtProjectStats | null>(null)

async function loadStats(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    stats.value = await fetchPtProjectStats(props.project.id)
  } catch (error) {
    loadError.value = getApiErrorMessage(error, '加载项目统计失败')
  } finally {
    loading.value = false
  }
}

function goTab(routeName: string): void {
  router.push({ name: routeName, params: { id: props.project.id } })
}

onMounted(loadStats)
watch(
  () => props.project.id,
  () => {
    void loadStats()
  },
)
</script>

<template>
  <div class="pt-overview-tab">
    <AsyncState :loading="loading" :error="loadError" @retry="loadStats">
      <div class="stats-grid">
        <el-card shadow="hover" class="stat-card" @click="goTab('pt-project-scenarios')">
          <div class="stat-value">{{ stats?.scenario_count ?? 0 }}</div>
          <div class="stat-label">压测详情</div>
        </el-card>
        <el-card shadow="hover" class="stat-card" @click="goTab('pt-project-runs')">
          <div class="stat-value">{{ stats?.run_count ?? 0 }}</div>
          <div class="stat-label">运行记录</div>
        </el-card>
      </div>

      <el-descriptions v-if="stats" :column="1" border class="meta-block">
        <el-descriptions-item label="项目描述">
          {{ project.description || '暂无描述' }}
        </el-descriptions-item>
        <el-descriptions-item label="最近运行">
          <template v-if="stats.last_run_at">
            {{ formatBeijingTime(stats.last_run_at) }}
            <el-tag size="small" class="run-tag">{{ stats.last_run_status }}</el-tag>
          </template>
          <span v-else class="muted">暂无运行记录</span>
        </el-descriptions-item>
      </el-descriptions>
    </AsyncState>
  </div>
</template>

<style scoped>
.pt-overview-tab {
  margin-top: 8px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  cursor: pointer;
  text-align: center;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #303133;
}

.stat-label {
  margin-top: 8px;
  color: #909399;
  font-size: 14px;
}

.meta-block {
  max-width: 640px;
}

.run-tag {
  margin-left: 8px;
}

.muted {
  color: #909399;
}
</style>
