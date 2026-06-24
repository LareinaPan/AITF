<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'

import type { Project } from '@/api/projects'
import { updateProject } from '@/api/projects'
import { getApiErrorMessage } from '@/api/request'

const props = defineProps<{
  project: Project
}>()

const emit = defineEmits<{
  updated: [project: Project]
}>()

const submitting = ref(false)
const formRef = ref<FormInstance>()

const form = reactive({
  feishu_webhook_url: '',
})

const rules: FormRules = {
  feishu_webhook_url: [{ max: 512, message: 'Webhook URL 最长 512 字符', trigger: 'blur' }],
}

function syncForm(): void {
  form.feishu_webhook_url = props.project.feishu_webhook_url ?? ''
}

async function handleSave(): Promise<void> {
  if (!formRef.value) {
    return
  }

  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) {
    return
  }

  submitting.value = true
  try {
    const updated = await updateProject(props.project.id, {
      feishu_webhook_url: form.feishu_webhook_url.trim() || null,
    })
    ElMessage.success('接口项目设置已保存')
    emit('updated', updated)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '保存接口项目设置失败'))
  } finally {
    submitting.value = false
  }
}

onMounted(syncForm)
</script>

<template>
  <div class="settings-tab">
    <el-card shadow="never">
      <template #header>
        <span>飞书通知</span>
      </template>
      <p class="settings-hint">
        测试计划执行完成后，将向该 Webhook 发送结果摘要（含 Allure 报告链接）。
      </p>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="140px">
        <el-form-item label="Webhook URL" prop="feishu_webhook_url">
          <el-input
            v-model="form.feishu_webhook_url"
            placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
            maxlength="512"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="handleSave">保存</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.settings-tab {
  margin-top: 8px;
}

.settings-hint {
  margin: 0 0 16px;
  color: #909399;
  font-size: 13px;
}
</style>
