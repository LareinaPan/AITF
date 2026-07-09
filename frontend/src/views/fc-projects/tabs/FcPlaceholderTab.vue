<script setup lang="ts">
import type { FcProject } from '@/api/fc-projects'

defineProps<{
  project: FcProject
  title: string
  phase: string
}>()
</script>

<template>
  <el-empty class="placeholder-panel" :description="`${title} — 将在 ${phase} 实现`">
    <p class="hint">当前功能项目：{{ project.name }}</p>
  </el-empty>
</template>

<style scoped>
.placeholder-panel {
  margin-top: 24px;
}

.hint {
  margin: 0;
  color: #909399;
  font-size: 14px;
}
</style>
