<script setup lang="ts">
import { computed } from 'vue'

import type { FcReviewReport } from '@/api/fc-generation'

const props = defineProps<{
  report: FcReviewReport | null
  coverageScore: number | null
}>()

const DIMENSION_LABELS: Record<string, string> = {
  positive: '正向场景',
  negative: '异常场景',
  boundary: '边界场景',
  permission: '权限场景',
  security: '安全场景',
  compatibility: '兼容场景',
}

const displayScore = computed(() => props.coverageScore ?? props.report?.coverage_score ?? null)

const dimensionItems = computed(() => {
  const scores = props.report?.dimension_scores ?? {}
  return Object.entries(DIMENSION_LABELS).map(([key, label]) => ({
    key,
    label,
    score: scores[key] ?? 0,
  }))
})

const gaps = computed(() => props.report?.gaps ?? [])
const suggestions = computed(() => props.report?.suggestions ?? [])
const featureChecklist = computed(() => props.report?.feature_checklist ?? [])
</script>

<template>
  <el-card shadow="never" class="review-report-panel">
    <template #header>
      <div class="panel-header">
        <span>AI 审查报告</span>
        <el-tag v-if="displayScore != null" :type="displayScore >= 80 ? 'success' : 'warning'">
          覆盖度 {{ displayScore.toFixed(1) }}%
        </el-tag>
      </div>
    </template>

    <el-empty v-if="!report && displayScore == null" description="暂无审查报告" />

    <template v-else>
      <div v-if="dimensionItems.length" class="dimension-grid">
        <div v-for="item in dimensionItems" :key="item.key" class="dimension-item">
          <span class="dimension-label">{{ item.label }}</span>
          <el-progress
            :percentage="item.score"
            :stroke-width="10"
            :color="item.score >= 80 ? '#67c23a' : '#e6a23c'"
          />
        </div>
      </div>

      <div v-if="featureChecklist.length" class="section">
        <h4>功能点覆盖</h4>
        <el-table :data="featureChecklist" size="small" stripe>
          <el-table-column prop="feature" label="功能点" min-width="140" />
          <el-table-column label="已覆盖" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="row.covered ? 'success' : 'danger'" size="small">
                {{ row.covered ? '是' : '否' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="case_count" label="用例数" width="90" align="center" />
        </el-table>
      </div>

      <div v-if="gaps.length" class="section">
        <h4>缺失点</h4>
        <ul class="text-list">
          <li v-for="(item, index) in gaps" :key="`gap-${index}`">{{ item }}</li>
        </ul>
      </div>

      <div v-if="suggestions.length" class="section">
        <h4>改进建议</h4>
        <ul class="text-list">
          <li v-for="(item, index) in suggestions" :key="`suggestion-${index}`">{{ item }}</li>
        </ul>
      </div>
    </template>
  </el-card>
</template>

<style scoped>
.review-report-panel {
  margin-bottom: 16px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.dimension-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.dimension-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.dimension-label {
  font-size: 13px;
  color: #606266;
}

.section {
  margin-top: 16px;
}

.section h4 {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
}

.text-list {
  margin: 0;
  padding-left: 18px;
  color: #606266;
  font-size: 13px;
}

.text-list li + li {
  margin-top: 4px;
}
</style>
