<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { fetchFcProjectStats, type FcProject, type FcProjectStats } from '@/api/fc-projects'
import { getApiErrorMessage } from '@/api/request'
import AsyncState from '@/components/common/AsyncState.vue'
import { formatBeijingTime } from '@/utils/datetime'

const props = defineProps<{
  project: FcProject
}>()

const router = useRouter()

const loading = ref(false)
const loadError = ref<string | null>(null)
const stats = ref<FcProjectStats | null>(null)

async function loadStats(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    stats.value = await fetchFcProjectStats(props.project.id)
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
  <div class="fc-overview-tab">
    <AsyncState :loading="loading" :error="loadError" @retry="loadStats">
      <div class="stats-grid">
        <el-card shadow="hover" class="stat-card" @click="goTab('fc-project-docs')">
          <div class="stat-value">{{ stats?.doc_count ?? 0 }}</div>
          <div class="stat-label">需求文档</div>
        </el-card>
        <el-card shadow="hover" class="stat-card" @click="goTab('fc-project-experience')">
          <div class="stat-value">{{ stats?.experience_case_count ?? 0 }}</div>
          <div class="stat-label">经验用例</div>
        </el-card>
        <el-card shadow="hover" class="stat-card" @click="goTab('fc-project-cases')">
          <div class="stat-value">{{ stats?.active_case_count ?? 0 }}</div>
          <div class="stat-label">正式用例</div>
        </el-card>
        <el-card shadow="hover" class="stat-card" @click="goTab('fc-project-review')">
          <div class="stat-value">{{ stats?.draft_case_count ?? 0 }}</div>
          <div class="stat-label">待复查用例</div>
        </el-card>
        <el-card shadow="hover" class="stat-card" @click="goTab('fc-project-history')">
          <div class="stat-value">{{ stats?.batch_count ?? 0 }}</div>
          <div class="stat-label">生成批次</div>
        </el-card>
      </div>

      <el-descriptions :column="1" border class="overview-panel">
        <el-descriptions-item label="功能项目名称">{{ project.name }}</el-descriptions-item>
        <el-descriptions-item label="功能项目描述">
          {{ project.description || '暂无描述' }}
        </el-descriptions-item>
        <el-descriptions-item label="创建人">{{ project.created_by_username }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">
          {{ formatBeijingTime(project.created_at) }}
        </el-descriptions-item>
        <el-descriptions-item label="最近生成">
          {{ stats?.last_batch_at ? formatBeijingTime(stats.last_batch_at) : '暂无' }}
        </el-descriptions-item>
      </el-descriptions>
    </AsyncState>
  </div>
</template>

<style scoped>
.fc-overview-tab {
  margin-top: 16px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card {
  cursor: pointer;
  text-align: center;
  transition: transform 0.15s ease;
}

.stat-card:hover {
  transform: translateY(-2px);
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #303133;
  line-height: 1.2;
}

.stat-label {
  margin-top: 6px;
  color: #909399;
  font-size: 13px;
}

.overview-panel {
  margin-top: 4px;
}
</style>
