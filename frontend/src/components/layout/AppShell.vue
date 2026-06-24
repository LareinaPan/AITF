<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const activeMenu = computed(() => {
  if (route.path.startsWith('/projects')) {
    return '/projects'
  }
  if (route.path.startsWith('/environments')) {
    return '/environments'
  }
  return route.path
})

async function handleLogout(): Promise<void> {
  await authStore.logout()
  ElMessage.success('已退出登录')
  await router.replace('/login')
}
</script>

<template>
  <el-container v-loading="!authStore.initialized" class="app-shell">
    <el-header class="app-header">
      <div class="brand" @click="router.push('/')">AITF</div>

      <el-menu
        mode="horizontal"
        :default-active="activeMenu"
        router
        class="nav-menu"
        :ellipsis="false"
      >
        <el-menu-item index="/">首页</el-menu-item>
        <el-menu-item index="/projects">接口项目</el-menu-item>
        <el-menu-item index="/environments">环境变量</el-menu-item>
      </el-menu>

      <div class="user-area">
        <span class="username">{{ authStore.user?.username }}</span>
        <el-button link type="primary" @click="handleLogout">退出</el-button>
      </div>
    </el-header>

    <el-main class="app-main">
      <RouterView />
    </el-main>
  </el-container>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: #f5f7fa;
}

.app-header {
  display: flex;
  align-items: center;
  gap: 24px;
  background: #fff;
  border-bottom: 1px solid #ebeef5;
  padding: 0 24px;
}

.brand {
  font-size: 20px;
  font-weight: 700;
  color: #409eff;
  cursor: pointer;
  white-space: nowrap;
}

.nav-menu {
  flex: 1;
  border-bottom: none;
}

.user-area {
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}

.username {
  color: #606266;
  font-size: 14px;
}

.app-main {
  padding: 24px;
}
</style>
