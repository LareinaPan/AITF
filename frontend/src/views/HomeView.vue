<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const appStore = useAppStore()
const authStore = useAuthStore()

interface ModuleEntry {
  key: string
  title: string
  description: string
  tag: string
  tagType: 'success' | 'info' | 'warning'
  available: boolean
  route?: string
}

const modules: ModuleEntry[] = [
  {
    key: 'api-test',
    title: '接口测试',
    description: '上传 OpenAPI、管理用例、执行计划并生成 Allure 报告',
    tag: '已上线',
    tagType: 'success',
    available: true,
    route: '/projects',
  },
  {
    key: 'functional-case',
    title: '功能用例生成',
    description: '基于需求文档，AI 辅助生成功能测试用例',
    tag: '已上线',
    tagType: 'success',
    available: true,
    route: '/fc-projects',
  },
  {
    key: 'performance-test',
    title: '性能测试',
    description: '配置压测场景，执行性能基准测试并查看分析报告',
    tag: '已上线',
    tagType: 'success',
    available: true,
    route: '/pt-projects',
  },
]

function handleModuleClick(module: ModuleEntry): void {
  if (module.available && module.route) {
    void router.push(module.route)
    return
  }
  ElMessage.info('还在构建中')
}
</script>

<template>
  <div class="home">
    <div class="home-intro">
      <h1 class="title">{{ appStore.title }}</h1>
      <p class="subtitle">欢迎回来，{{ authStore.user?.username }}！请选择要进入的功能模块</p>
    </div>

    <el-row :gutter="20">
      <el-col v-for="module in modules" :key="module.key" :xs="24" :sm="12" :lg="8">
        <el-card
          shadow="hover"
          class="module-card"
          :class="{ 'module-card--disabled': !module.available }"
          @click="handleModuleClick(module)"
        >
          <div class="module-header">
            <h2 class="module-title">{{ module.title }}</h2>
            <el-tag :type="module.tagType" size="small">{{ module.tag }}</el-tag>
          </div>
          <p class="module-desc">{{ module.description }}</p>
          <el-button
            :type="module.available ? 'primary' : 'default'"
            link
            class="module-action"
          >
            {{ module.available ? '进入模块' : '敬请期待' }}
          </el-button>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.home {
  max-width: 1080px;
  margin: 0 auto;
}

.home-intro {
  margin-bottom: 24px;
}

.title {
  margin: 0;
  font-size: 28px;
  font-weight: 600;
  color: #303133;
}

.subtitle {
  margin: 10px 0 0;
  color: #606266;
  font-size: 15px;
}

.module-card {
  margin-bottom: 20px;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
  min-height: 180px;
}

.module-card:hover {
  transform: translateY(-2px);
}

.module-card--disabled {
  cursor: pointer;
  opacity: 0.92;
}

.module-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.module-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.module-desc {
  margin: 0;
  min-height: 44px;
  color: #606266;
  font-size: 14px;
  line-height: 1.6;
}

.module-action {
  margin-top: 16px;
  padding: 0;
  font-weight: 600;
}
</style>
