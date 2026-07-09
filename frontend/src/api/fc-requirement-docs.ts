import request from './request'
import { postFormData } from './form-upload'

export interface FcRequirementDoc {
  id: string
  fc_project_id: string
  filename: string
  file_type: string
  file_size: number
  parse_status: 'pending' | 'success' | 'failed'
  parse_error: string | null
  parsed_text_preview: string | null
  uploaded_by: string
  uploaded_by_username: string
  created_at: string
}

export interface FcRequirementDocDetail extends FcRequirementDoc {
  parsed_text: string | null
}

export interface FcRequirementDocUploadResult {
  doc: FcRequirementDoc
}

export async function fetchFcRequirementDocs(projectId: string): Promise<FcRequirementDoc[]> {
  const { data } = await request.get<FcRequirementDoc[]>(`/fc-projects/${projectId}/docs`)
  return data
}

export async function fetchFcRequirementDoc(
  projectId: string,
  docId: string,
): Promise<FcRequirementDocDetail> {
  const { data } = await request.get<FcRequirementDocDetail>(
    `/fc-projects/${projectId}/docs/${docId}`,
  )
  return data
}

export const FC_REQUIREMENT_DOC_EXTENSIONS = ['.txt', '.md', '.docx'] as const

export function isSupportedFcRequirementDoc(file: File): boolean {
  const lowerName = file.name.toLowerCase()
  return FC_REQUIREMENT_DOC_EXTENSIONS.some((ext) => lowerName.endsWith(ext))
}

export async function uploadFcRequirementDoc(
  projectId: string,
  file: File,
): Promise<FcRequirementDocUploadResult> {
  if (!isSupportedFcRequirementDoc(file)) {
    throw new Error('仅支持 .txt / .md / .docx 格式的需求文档')
  }

  return postFormData<FcRequirementDocUploadResult>(
    `/fc-projects/${projectId}/docs/upload`,
    file,
    'file',
    '上传需求文档失败',
  )
}

export async function deleteFcRequirementDoc(projectId: string, docId: string): Promise<void> {
  await request.delete(`/fc-projects/${projectId}/docs/${docId}`)
}

export function parseStatusLabel(status: FcRequirementDoc['parse_status']): string {
  switch (status) {
    case 'success':
      return '解析成功'
    case 'failed':
      return '解析失败'
    default:
      return '待解析'
  }
}

export function parseStatusTagType(
  status: FcRequirementDoc['parse_status'],
): 'success' | 'danger' | 'info' {
  switch (status) {
    case 'success':
      return 'success'
    case 'failed':
      return 'danger'
    default:
      return 'info'
  }
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
