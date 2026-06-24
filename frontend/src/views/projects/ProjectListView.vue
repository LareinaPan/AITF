<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'

import { fetchDashboardStats, type DashboardStats } from '@/api/dashboard'
import {
  createProject,
  deleteProject,
  fetchProjects,
  type Project,
} from '@/api/projects'
import { getApiErrorMessage } from '@/api/request'
import { formatBeijingTime } from '@/utils/datetime'
import AsyncState from '@/components/common/AsyncState.vue'

const router = useRouter()

const loading = ref(false)
const loadError = ref<string | null>(null)
const projects = ref<Project[]>([])
const stats = ref<DashboardStats | null>(null)
const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()

const form = reactive({
  name: '',
  description: '',
})

const rules: FormRules = {
  name: [
    { required: true, message: '请输入接口项目名称', trigger: 'blur' },
    { min: 1, max: 128, message: '接口项目名称长度为 1-128 个字符', trigger: 'blur' },
  ],
}

interface ProjectRow extends Project {
  apis: number
  cases: number
}

const projectRows = computed<ProjectRow[]>(() => {
  const statsMap = new Map(
    (stats.value?.by_project ?? []).map((item) => [item.project_id, item]),
  )
  return projects.value.map((project) => {
    const projectStats = statsMap.get(project.id)
    return {
      ...project,
      apis: projectStats?.apis ?? 0,
      cases: projectStats?.cases ?? 0,
    }
  })
})

async function loadPageData(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    const [projectList, dashboardStats] = await Promise.all([
      fetchProjects(),
      fetchDashboardStats(),
    ])
    projects.value = projectList
    stats.value = dashboardStats
  } catch (error) {
    loadError.value = getApiErrorMessage(error, '加载接口项目列表失败')
  } finally {
    loading.value = false
  }
}

function openCreateDialog(): void {
  form.name = ''
  form.description = ''
  dialogVisible.value = true
}

async function handleCreate(): Promise<void> {
  if (!formRef.value) {
    return
  }

  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) {
    return
  }

  submitting.value = true
  try {
    const project = await createProject({
      name: form.name.trim(),
      description: form.description.trim() || null,
    })
    ElMessage.success('接口项目创建成功')
    dialogVisible.value = false
    await router.push(`/projects/${project.id}`)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '创建接口项目失败'))
  } finally {
    submitting.value = false
  }
}

async function handleDelete(project: Project): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定删除接口项目「${project.name}」吗？此操作不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    await deleteProject(project.id)
    ElMessage.success('接口项目已删除')
    await loadPageData()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(getApiErrorMessage(error, '删除接口项目失败'))
    }
  }
}

onMounted(loadPageData)
</script>

<template>
  <div class="project-list-page">
    <AsyncState :loading="loading" :error="loadError" @retry="loadPageData">
    <el-row :gutter="16" class="stat-row">
      <el-col :xs="24" :sm="8">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-label">接口项目</div>
          <div class="stat-value">{{ stats?.by_project.length ?? projects.length }}</div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-label">接口</div>
          <div class="stat-value">{{ stats?.total_apis ?? 0 }}</div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-label">用例</div>
          <div class="stat-value">{{ stats?.total_cases ?? 0 }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never">
      <template #header>
        <div class="page-header">
          <div>
            <h2 class="page-title">接口项目列表</h2>
            <p class="page-subtitle">管理接口测试模块下的项目，全员可见、共同编辑</p>
          </div>
          <el-button type="primary" @click="openCreateDialog">创建接口项目</el-button>
        </div>
      </template>

      <el-table
        v-loading="loading"
        :data="projectRows"
        stripe
        empty-text="暂无接口项目，点击右上角创建"
      >
        <el-table-column prop="name" label="接口项目名称" min-width="160">
          <template #default="{ row }">
            <el-link type="primary" @click="router.push(`/projects/${row.id}`)">
              {{ row.name }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
        <el-table-column prop="apis" label="接口" width="100" align="center" />
        <el-table-column prop="cases" label="用例" width="100" align="center" />
        <el-table-column label="创建时间" min-width="170">
          <template #default="{ row }">
            {{ formatBeijingTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="router.push(`/projects/${row.id}`)">
              进入详情
            </el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" title="创建接口项目" width="480px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="接口项目名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入接口项目名称" maxlength="128" show-word-limit />
        </el-form-item>
        <el-form-item label="接口项目描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="4"
            placeholder="可选，简要描述接口项目用途"
            maxlength="2000"
            show-word-limit
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>
    </AsyncState>
  </div>
</template>

<style scoped>
.project-list-page {
  max-width: 1100px;
  margin: 0 auto;
}

.stat-row {
  margin-bottom: 16px;
}

.stat-card {
  margin-bottom: 16px;
}

.stat-label {
  font-size: 14px;
  color: #909399;
}

.stat-value {
  margin-top: 8px;
  font-size: 28px;
  font-weight: 700;
  color: #303133;
  line-height: 1.2;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.page-subtitle {
  margin: 6px 0 0;
  color: #909399;
  font-size: 14px;
}
</style>
