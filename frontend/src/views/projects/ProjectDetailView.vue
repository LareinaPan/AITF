<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { fetchProject, type Project } from '@/api/projects'
import { getApiErrorMessage } from '@/api/request'
import AsyncState from '@/components/common/AsyncState.vue'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const loadError = ref<string | null>(null)
const project = ref<Project | null>(null)

const projectId = computed(() => route.params.id as string)

const tabRouteNames: Record<string, string> = {
  overview: 'project-overview',
  apis: 'project-apis',
  cases: 'project-cases',
  'ai-review': 'project-ai-review',
  plans: 'project-plans',
  settings: 'project-settings',
}

const routeNameToTab: Record<string, string> = {
  ...Object.fromEntries(Object.entries(tabRouteNames).map(([tab, name]) => [name, tab])),
  'project-case-create': 'cases',
  'project-case-edit': 'cases',
  'project-plan-detail': 'plans',
}

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
    project.value = await fetchProject(projectId.value)
  } catch (error) {
    project.value = null
    loadError.value = getApiErrorMessage(error, '加载接口项目详情失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadProject)
watch(projectId, loadProject)
</script>

<template>
  <AsyncState :loading="loading" :error="loadError" @retry="loadProject">
    <div class="project-detail-page">
      <el-page-header @back="router.push('/projects')">
        <template #content>
          <span class="project-title">{{ project?.name ?? '接口项目详情' }}</span>
        </template>
      </el-page-header>

      <el-card v-if="project" shadow="never" class="detail-card">
        <el-tabs v-model="activeTab">
          <el-tab-pane label="概览" name="overview" />
          <el-tab-pane label="接口管理" name="apis" />
          <el-tab-pane label="用例" name="cases" />
          <el-tab-pane label="AI 确认" name="ai-review" />
          <el-tab-pane label="测试计划" name="plans" />
          <el-tab-pane label="设置" name="settings" />
        </el-tabs>

        <RouterView v-slot="{ Component }">
          <component :is="Component" :project="project" @updated="project = $event" />
        </RouterView>
      </el-card>
    </div>
  </AsyncState>
</template>

<style scoped>
.project-detail-page {
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
