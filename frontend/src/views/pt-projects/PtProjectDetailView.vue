<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { fetchPtProject, type PtProject } from '@/api/pt-projects'
import { getApiErrorMessage } from '@/api/request'
import AsyncState from '@/components/common/AsyncState.vue'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const loadError = ref<string | null>(null)
const project = ref<PtProject | null>(null)

const projectId = computed(() => route.params.id as string)

const tabRouteNames: Record<string, string> = {
  overview: 'pt-project-overview',
  scenarios: 'pt-project-scenarios',
  runs: 'pt-project-runs',
}

const routeNameToTab: Record<string, string> = Object.fromEntries(
  Object.entries(tabRouteNames).map(([tab, name]) => [name, tab]),
)

const activeTab = computed({
  get() {
    return routeNameToTab[route.name as string] ?? 'overview'
  },
  set(tab: string) {
    const routeName = tabRouteNames[tab]
    if (routeName) {
      router.push({ name: routeName, params: { id: projectId.value } })
    }
  },
})

async function loadProject(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    project.value = await fetchPtProject(projectId.value)
  } catch (error) {
    project.value = null
    loadError.value = getApiErrorMessage(error, '加载压测项目详情失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadProject)
watch(projectId, loadProject)
</script>

<template>
  <AsyncState :loading="loading" :error="loadError" @retry="loadProject">
    <div class="pt-project-detail-page">
      <el-page-header @back="router.push('/pt-projects')">
        <template #content>
          <span class="project-title">{{ project?.name ?? '压测项目详情' }}</span>
        </template>
      </el-page-header>

      <el-card v-if="project" shadow="never" class="detail-card">
        <el-tabs v-model="activeTab">
          <el-tab-pane label="概览" name="overview" />
          <el-tab-pane label="压测详情" name="scenarios" />
          <el-tab-pane label="运行记录" name="runs" />
        </el-tabs>

        <RouterView v-slot="{ Component }">
          <component :is="Component" :project="project" />
        </RouterView>
      </el-card>
    </div>
  </AsyncState>
</template>

<style scoped>
.pt-project-detail-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.project-title {
  font-size: 18px;
  font-weight: 600;
}

.detail-card {
  margin-top: 4px;
}
</style>
