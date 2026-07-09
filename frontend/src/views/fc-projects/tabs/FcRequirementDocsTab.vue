<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadInstance, UploadRequestOptions } from 'element-plus'

import type { FcProject } from '@/api/fc-projects'
import {
  deleteFcRequirementDoc,
  fetchFcRequirementDoc,
  fetchFcRequirementDocs,
  formatFileSize,
  parseStatusLabel,
  parseStatusTagType,
  uploadFcRequirementDoc,
  type FcRequirementDoc,
  type FcRequirementDocDetail,
} from '@/api/fc-requirement-docs'
import { getApiErrorMessage } from '@/api/request'
import { formatBeijingTime } from '@/utils/datetime'
import AsyncState from '@/components/common/AsyncState.vue'

const props = defineProps<{
  project: FcProject
}>()

const loading = ref(false)
const loadError = ref<string | null>(null)
const uploading = ref(false)
const deletingId = ref<string | null>(null)
const docs = ref<FcRequirementDoc[]>([])

const uploadRef = ref<UploadInstance>()
const detailVisible = ref(false)
const detailLoading = ref(false)
const selectedDoc = ref<FcRequirementDocDetail | null>(null)

async function loadDocs(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    docs.value = await fetchFcRequirementDocs(props.project.id)
  } catch (error) {
    loadError.value = getApiErrorMessage(error, '加载需求文档列表失败')
  } finally {
    loading.value = false
  }
}

async function handleUpload(options: UploadRequestOptions): Promise<void> {
  const { file, onError, onSuccess } = options
  uploading.value = true
  try {
    const result = await uploadFcRequirementDoc(props.project.id, file)
    if (!result?.doc) {
      throw new Error('上传响应格式异常，请刷新后重试')
    }
    const status = result.doc.parse_status
    if (status === 'success') {
      ElMessage.success(`上传成功：${result.doc.filename} 已解析`)
    } else {
      ElMessage.warning(`上传完成但解析失败：${result.doc.parse_error ?? '未知错误'}`)
    }
    onSuccess(result)
    await loadDocs()
  } catch (error) {
    onError(error as Error)
    ElMessage.error(getApiErrorMessage(error, '上传需求文档失败'))
  } finally {
    uploading.value = false
    uploadRef.value?.clearFiles()
  }
}

async function openDetail(doc: FcRequirementDoc): Promise<void> {
  detailVisible.value = true
  detailLoading.value = true
  selectedDoc.value = null
  try {
    selectedDoc.value = await fetchFcRequirementDoc(props.project.id, doc.id)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '加载文档详情失败'))
    detailVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

async function handleDelete(doc: FcRequirementDoc): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定删除需求文档「${doc.filename}」吗？此操作不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    deletingId.value = doc.id
    await deleteFcRequirementDoc(props.project.id, doc.id)
    ElMessage.success('需求文档已删除')
    if (selectedDoc.value?.id === doc.id) {
      detailVisible.value = false
      selectedDoc.value = null
    }
    await loadDocs()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(getApiErrorMessage(error, '删除需求文档失败'))
    }
  } finally {
    deletingId.value = null
  }
}

onMounted(loadDocs)
watch(
  () => props.project.id,
  () => {
    void loadDocs()
  },
)
</script>

<template>
  <div class="fc-docs-tab">
    <AsyncState :loading="loading" :error="loadError" @retry="loadDocs">
      <div class="toolbar">
        <div class="toolbar-text">
          <p class="hint">支持上传 .txt / .md / .docx 格式需求文档，单文件最大 10 MB</p>
        </div>
        <el-upload
          ref="uploadRef"
          :show-file-list="false"
          accept=".txt,.md,.docx"
          :disabled="uploading"
          :http-request="handleUpload"
        >
          <el-button type="primary" :loading="uploading">上传需求文档</el-button>
        </el-upload>
      </div>

      <el-table
        v-loading="loading"
        :data="docs"
        stripe
        empty-text="暂无需求文档，点击右上角上传"
      >
        <el-table-column prop="filename" label="文件名" min-width="180" />
        <el-table-column prop="file_type" label="类型" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small">{{ row.file_type.toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="大小" width="100" align="center">
          <template #default="{ row }">
            {{ formatFileSize(row.file_size) }}
          </template>
        </el-table-column>
        <el-table-column label="解析状态" width="120" align="center">
          <template #default="{ row }">
            <el-tag :type="parseStatusTagType(row.parse_status)" size="small">
              {{ parseStatusLabel(row.parse_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="uploaded_by_username" label="上传人" width="120" />
        <el-table-column label="上传时间" min-width="170">
          <template #default="{ row }">
            {{ formatBeijingTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">查看</el-button>
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
    </AsyncState>

    <el-drawer v-model="detailVisible" title="需求文档详情" size="520px" destroy-on-close>
      <div v-loading="detailLoading">
        <template v-if="selectedDoc">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="文件名">{{ selectedDoc.filename }}</el-descriptions-item>
            <el-descriptions-item label="解析状态">
              <el-tag :type="parseStatusTagType(selectedDoc.parse_status)" size="small">
                {{ parseStatusLabel(selectedDoc.parse_status) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item v-if="selectedDoc.parse_error" label="失败原因">
              {{ selectedDoc.parse_error }}
            </el-descriptions-item>
            <el-descriptions-item label="上传人">
              {{ selectedDoc.uploaded_by_username }}
            </el-descriptions-item>
            <el-descriptions-item label="上传时间">
              {{ formatBeijingTime(selectedDoc.created_at) }}
            </el-descriptions-item>
          </el-descriptions>

          <div v-if="selectedDoc.parsed_text" class="parsed-text-block">
            <h4 class="block-title">解析文本</h4>
            <pre class="parsed-text">{{ selectedDoc.parsed_text }}</pre>
          </div>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.fc-docs-tab {
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

.parsed-text-block {
  margin-top: 20px;
}

.block-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.parsed-text {
  margin: 0;
  padding: 12px;
  max-height: 420px;
  overflow: auto;
  background: #f5f7fa;
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.6;
}
</style>
