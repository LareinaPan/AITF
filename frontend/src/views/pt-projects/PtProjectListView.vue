<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  createPtProject,
  deletePtProject,
  fetchPtProjects,
  type PtProject,
} from '@/api/pt-projects'
import { getApiErrorMessage } from '@/api/request'
import { formatBeijingTime } from '@/utils/datetime'
import AsyncState from '@/components/common/AsyncState.vue'

const router = useRouter()

const loading = ref(false)
const loadError = ref<string | null>(null)
const projects = ref<PtProject[]>([])
const dialogVisible = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()

const form = reactive({
  name: '',
  description: '',
})

const rules: FormRules = {
  name: [
    { required: true, message: '请输入压测项目名称', trigger: 'blur' },
    { min: 1, max: 128, message: '压测项目名称长度为 1-128 个字符', trigger: 'blur' },
  ],
}

async function loadPageData(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    projects.value = await fetchPtProjects()
  } catch (error) {
    loadError.value = getApiErrorMessage(error, '加载压测项目列表失败')
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
    const project = await createPtProject({
      name: form.name.trim(),
      description: form.description.trim() || null,
    })
    ElMessage.success('压测项目创建成功')
    dialogVisible.value = false
    await router.push(`/pt-projects/${project.id}`)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '创建压测项目失败'))
  } finally {
    submitting.value = false
  }
}

async function handleDelete(project: PtProject): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定删除压测项目「${project.name}」吗？此操作不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    await deletePtProject(project.id)
    ElMessage.success('压测项目已删除')
    await loadPageData()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(getApiErrorMessage(error, '删除压测项目失败'))
    }
  }
}

onMounted(loadPageData)
</script>

<template>
  <div class="pt-project-list-page">
    <AsyncState :loading="loading" :error="loadError" @retry="loadPageData">
      <el-card shadow="never">
        <template #header>
          <div class="page-header">
            <div>
              <h2 class="page-title">压测项目列表</h2>
              <p class="page-subtitle">管理性能测试模块下的项目，全员可见、共同编辑</p>
            </div>
            <el-button type="primary" @click="openCreateDialog">创建压测项目</el-button>
          </div>
        </template>

        <el-table
          v-loading="loading"
          :data="projects"
          stripe
          empty-text="暂无压测项目，点击右上角创建"
        >
          <el-table-column prop="name" label="压测项目名称" min-width="160">
            <template #default="{ row }">
              <el-link type="primary" @click="router.push(`/pt-projects/${row.id}`)">
                {{ row.name }}
              </el-link>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
          <el-table-column prop="created_by_username" label="创建人" width="120" />
          <el-table-column label="创建时间" min-width="170">
            <template #default="{ row }">
              {{ formatBeijingTime(row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="160" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="router.push(`/pt-projects/${row.id}`)">
                进入详情
              </el-button>
              <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-dialog v-model="dialogVisible" title="创建压测项目" width="480px" destroy-on-close>
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
          <el-form-item label="压测项目名称" prop="name">
            <el-input
              v-model="form.name"
              placeholder="请输入压测项目名称"
              maxlength="128"
              show-word-limit
            />
          </el-form-item>
          <el-form-item label="压测项目描述">
            <el-input
              v-model="form.description"
              type="textarea"
              :rows="4"
              placeholder="可选，简要描述压测项目用途"
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
.pt-project-list-page {
  max-width: 1100px;
  margin: 0 auto;
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
