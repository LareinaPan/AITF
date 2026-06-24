<script setup lang="ts">
defineProps<{
  loading?: boolean
  error?: string | null
  loadingText?: string
}>()

defineEmits<{
  retry: []
}>()
</script>

<template>
  <div
    v-loading="loading"
    :element-loading-text="loadingText"
    class="async-state"
  >
    <el-result v-if="error && !loading" icon="warning" :title="error" sub-title="请检查网络或后端服务后重试">
      <template #extra>
        <el-button type="primary" @click="$emit('retry')">重试</el-button>
      </template>
    </el-result>
    <slot v-else />
  </div>
</template>

<style scoped>
.async-state {
  min-height: 120px;
}
</style>
