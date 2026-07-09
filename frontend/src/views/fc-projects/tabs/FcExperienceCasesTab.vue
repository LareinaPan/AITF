<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules, UploadInstance, UploadRequestOptions } from 'element-plus'

import type { FcProject } from '@/api/fc-projects'
import {
  FC_CASE_TYPE_OPTIONS,
  FC_PRIORITY_OPTIONS,
  caseTypeLabel,
  createFcExperienceCase,
  deleteFcExperienceCase,
  downloadFcExperienceTemplate,
  fetchFcExperienceCases,
  importFcExperienceCases,
  updateFcExperienceCase,
  type FcExperienceCase,
  type FcCaseType,
  type FcPriority,
} from '@/api/fc-experience-cases'
import { getApiErrorMessage } from '@/api/request'
import { formatBeijingTime } from '@/utils/datetime'
import AsyncState from '@/components/common/AsyncState.vue'

const props = defineProps<{
  project: FcProject
}>()

const loading = ref(false)
const loadError = ref<string | null>(null)
const submitting = ref(false)
const importing = ref(false)
const deletingId = ref<string | null>(null)
const cases = ref<FcExperienceCase[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

const dialogVisible = ref(false)
const editingCase = ref<FcExperienceCase | null>(null)
const formRef = ref<FormInstance>()
const uploadRef = ref<UploadInstance>()

const form = reactive({
  case_no: '',
  module: '',
  title: '',
  preconditions: '',
  steps: '',
  expected_result: '',
  priority: 'P2' as FcPriority,
  case_type: 'positive' as FcCaseType,
  tags: '',
})

const rules: FormRules = {
  module: [{ required: true, message: '请输入功能模块', trigger: 'blur' }],
  title: [{ required: true, message: '请输入用例标题', trigger: 'blur' }],
  steps: [{ required: true, message: '请输入测试步骤', trigger: 'blur' }],
  expected_result: [{ required: true, message: '请输入预期结果', trigger: 'blur' }],
}

function resetForm(): void {
  form.case_no = ''
  form.module = ''
  form.title = ''
  form.preconditions = ''
  form.steps = ''
  form.expected_result = ''
  form.priority = 'P2'
  form.case_type = 'positive'
  form.tags = ''
}

async function loadCases(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    const result = await fetchFcExperienceCases(props.project.id, {
      page: page.value,
      page_size: pageSize.value,
    })
    cases.value = result.items
    total.value = result.total
    if (total.value > 0 && cases.value.length === 0 && page.value > 1) {
      page.value -= 1
      await loadCases()
    }
  } catch (error) {
    loadError.value = getApiErrorMessage(error, '加载经验用例失败')
  } finally {
    loading.value = false
  }
}

function handlePageChange(nextPage: number): void {
  page.value = nextPage
  void loadCases()
}

function handleSizeChange(nextSize: number): void {
  pageSize.value = nextSize
  page.value = 1
  void loadCases()
}

function openCreateDialog(): void {
  editingCase.value = null
  resetForm()
  dialogVisible.value = true
}

function openEditDialog(item: FcExperienceCase): void {
  editingCase.value = item
  form.case_no = item.case_no ?? ''
  form.module = item.module
  form.title = item.title
  form.preconditions = item.preconditions ?? ''
  form.steps = item.steps
  form.expected_result = item.expected_result
  form.priority = item.priority
  form.case_type = item.case_type
  form.tags = item.tags ?? ''
  dialogVisible.value = true
}

async function handleSubmit(): Promise<void> {
  if (!formRef.value) {
    return
  }

  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) {
    return
  }

  submitting.value = true
  const payload = {
    case_no: form.case_no.trim() || null,
    module: form.module.trim(),
    title: form.title.trim(),
    preconditions: form.preconditions.trim() || null,
    steps: form.steps.trim(),
    expected_result: form.expected_result.trim(),
    priority: form.priority,
    case_type: form.case_type,
    tags: form.tags.trim() || null,
  }

  try {
    if (editingCase.value) {
      await updateFcExperienceCase(props.project.id, editingCase.value.id, payload)
      ElMessage.success('经验用例已更新')
    } else {
      await createFcExperienceCase(props.project.id, payload)
      ElMessage.success('经验用例已添加')
    }
    dialogVisible.value = false
    page.value = 1
    await loadCases()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '保存经验用例失败'))
  } finally {
    submitting.value = false
  }
}

async function handleDelete(item: FcExperienceCase): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定删除经验用例「${item.title}」吗？此操作不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    deletingId.value = item.id
    await deleteFcExperienceCase(props.project.id, item.id)
    ElMessage.success('经验用例已删除')
    await loadCases()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(getApiErrorMessage(error, '删除经验用例失败'))
    }
  } finally {
    deletingId.value = null
  }
}

async function handleImport(options: UploadRequestOptions): Promise<void> {
  const { file, onError, onSuccess } = options
  importing.value = true
  try {
    const result = await importFcExperienceCases(props.project.id, file)
    if (result.imported_count > 0) {
      ElMessage.success(`成功导入 ${result.imported_count} 条经验用例`)
    }
    if (result.rejected_count > 0) {
      ElMessage.warning(`${result.rejected_count} 行导入失败，请检查 Excel 内容`)
    }
    onSuccess(result)
    page.value = 1
    await loadCases()
  } catch (error) {
    onError(error as Error)
    ElMessage.error(getApiErrorMessage(error, '导入经验用例失败'))
  } finally {
    importing.value = false
    uploadRef.value?.clearFiles()
  }
}

async function handleDownloadTemplate(): Promise<void> {
  try {
    await downloadFcExperienceTemplate(props.project.id)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '下载模板失败'))
  }
}

onMounted(loadCases)
watch(
  () => props.project.id,
  () => {
    page.value = 1
    void loadCases()
  },
)
</script>

<template>
  <div class="fc-experience-tab">
    <AsyncState :loading="loading" :error="loadError" @retry="loadCases">
      <div class="toolbar">
        <p class="hint">维护项目经验用例，AI 生成时可勾选引用以提升覆盖度</p>
        <div class="toolbar-actions">
          <el-button @click="handleDownloadTemplate">下载 Excel 模板</el-button>
          <el-upload
            ref="uploadRef"
            :show-file-list="false"
            accept=".xlsx"
            :disabled="importing"
            :http-request="handleImport"
          >
            <el-button :loading="importing">Excel 导入</el-button>
          </el-upload>
          <el-button type="primary" @click="openCreateDialog">添加经验用例</el-button>
        </div>
      </div>

      <el-table
        v-loading="loading"
        :data="cases"
        stripe
        empty-text="暂无经验用例，可手动添加或 Excel 导入"
      >
        <el-table-column prop="case_no" label="编号" width="120">
          <template #default="{ row }">
            {{ row.case_no || '—' }}
          </template>
        </el-table-column>
        <el-table-column prop="module" label="功能模块" min-width="120" show-overflow-tooltip />
        <el-table-column prop="title" label="用例标题" min-width="160" show-overflow-tooltip />
        <el-table-column label="类型" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small">{{ caseTypeLabel(row.case_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="90" align="center" />
        <el-table-column label="创建时间" min-width="170">
          <template #default="{ row }">
            {{ formatBeijingTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEditDialog(row)">编辑</el-button>
            <el-button
              link
              type="danger"
              :loading="deletingId === row.id"
              @click="handleDelete(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="total > 0" class="pagination-bar">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </AsyncState>

    <el-dialog
      v-model="dialogVisible"
      :title="editingCase ? '编辑经验用例' : '添加经验用例'"
      width="640px"
      destroy-on-close
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
        <el-form-item label="用例编号">
          <el-input v-model="form.case_no" placeholder="可选，如 EXP-001" maxlength="64" />
        </el-form-item>
        <el-form-item label="功能模块" prop="module">
          <el-input v-model="form.module" placeholder="如：用户登录" maxlength="128" />
        </el-form-item>
        <el-form-item label="用例标题" prop="title">
          <el-input v-model="form.title" placeholder="简短描述" maxlength="256" />
        </el-form-item>
        <el-form-item label="前置条件">
          <el-input
            v-model="form.preconditions"
            type="textarea"
            :rows="2"
            placeholder="可选"
            maxlength="4000"
          />
        </el-form-item>
        <el-form-item label="测试步骤" prop="steps">
          <el-input
            v-model="form.steps"
            type="textarea"
            :rows="4"
            placeholder="多步请换行分隔"
            maxlength="8000"
          />
        </el-form-item>
        <el-form-item label="预期结果" prop="expected_result">
          <el-input
            v-model="form.expected_result"
            type="textarea"
            :rows="3"
            maxlength="8000"
          />
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="form.priority" style="width: 120px">
            <el-option v-for="item in FC_PRIORITY_OPTIONS" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="用例类型">
          <el-select v-model="form.case_type" style="width: 160px">
            <el-option
              v-for="item in FC_CASE_TYPE_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="form.tags" placeholder="可选，逗号分隔" maxlength="256" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.fc-experience-tab {
  margin-top: 16px;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.hint {
  margin: 0;
  color: #909399;
  font-size: 13px;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
