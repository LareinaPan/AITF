<script setup lang="ts">
import type { Project } from '@/api/projects'
import { formatBeijingTime } from '@/utils/datetime'

defineProps<{
  project: Project
}>()
</script>

<template>
  <el-descriptions :column="1" border class="overview-panel">
    <el-descriptions-item label="接口项目名称">{{ project.name }}</el-descriptions-item>
    <el-descriptions-item label="接口项目描述">
      {{ project.description || '暂无描述' }}
    </el-descriptions-item>
    <el-descriptions-item label="飞书 Webhook">
      {{ project.feishu_webhook_url || '未配置' }}
    </el-descriptions-item>
    <el-descriptions-item label="创建人">{{ project.created_by_username }}</el-descriptions-item>
    <el-descriptions-item label="创建时间">{{ formatBeijingTime(project.created_at) }}</el-descriptions-item>
  </el-descriptions>
</template>

<style scoped>
.overview-panel {
  margin-top: 16px;
}
</style>
