<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { fetchFcProject, type FcProject } from '@/api/fc-projects'
import { getApiErrorMessage } from '@/api/request'
import AsyncState from '@/components/common/AsyncState.vue'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const loadError = ref<string | null>(null)
const project = ref<FcProject | null>(null)

const projectId = computed(() => route.params.id as string)

const tabRouteNames: Record<string, string> = {
  overview: 'fc-project-overview',
  docs: 'fc-project-docs',
  experience: 'fc-project-experience',
  generate: 'fc-project-generate',
  review: 'fc-project-review',
  cases: 'fc-project-cases',
  history: 'fc-project-history',
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
    project.value = await fetchFcProject(projectId.value)
  } catch (error) {
    project.value = null
    loadError.value = getApiErrorMessage(error, '加载功能项目详情失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadProject)
watch(projectId, loadProject)
</script>

<template>
  <AsyncState :loading="loading" :error="loadError" @retry="loadProject">
    <div class="fc-project-detail-page">
      <el-page-header @back="router.push('/fc-projects')">
        <template #content>
          <span class="project-title">{{ project?.name ?? '功能项目详情' }}</span>
        </template>
      </el-page-header>

      <el-card v-if="project" shadow="never" class="detail-card">
        <el-tabs v-model="activeTab">
          <el-tab-pane label="概览" name="overview" />
          <el-tab-pane label="需求文档" name="docs" />
          <el-tab-pane label="经验用例" name="experience" />
          <el-tab-pane label="AI 生成" name="generate" />
          <el-tab-pane label="用例复查" name="review" />
          <el-tab-pane label="用例库" name="cases" />
          <el-tab-pane label="生成历史" name="history" />
        </el-tabs>

        <RouterView v-slot="{ Component }">
          <component :is="Component" :project="project" />
        </RouterView>
      </el-card>
    </div>
  </AsyncState>
</template>

<style scoped>
.fc-project-detail-page {
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
