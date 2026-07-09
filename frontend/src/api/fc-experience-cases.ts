import request from './request'
import { postFormData } from './form-upload'
import { getStoredToken } from '@/utils/auth-storage'

const apiBaseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

export type FcCaseType =
  | 'positive'
  | 'negative'
  | 'boundary'
  | 'permission'
  | 'security'
  | 'compatibility'

export type FcPriority = 'P0' | 'P1' | 'P2' | 'P3'

export interface FcExperienceCase {
  id: string
  fc_project_id: string
  case_no: string | null
  module: string
  title: string
  preconditions: string | null
  steps: string
  expected_result: string
  priority: FcPriority
  case_type: FcCaseType
  tags: string | null
  created_at: string
}

export interface FcExperienceCasePayload {
  case_no?: string | null
  module: string
  title: string
  preconditions?: string | null
  steps: string
  expected_result: string
  priority?: FcPriority
  case_type?: FcCaseType
  tags?: string | null
}

export interface FcExperienceImportResult {
  imported_count: number
  rejected_count: number
  errors: string[]
  cases: FcExperienceCase[]
}

export const FC_CASE_TYPE_OPTIONS: Array<{ label: string; value: FcCaseType }> = [
  { label: '正向', value: 'positive' },
  { label: '异常', value: 'negative' },
  { label: '边界', value: 'boundary' },
  { label: '权限', value: 'permission' },
  { label: '安全', value: 'security' },
  { label: '兼容', value: 'compatibility' },
]

export const FC_PRIORITY_OPTIONS: FcPriority[] = ['P0', 'P1', 'P2', 'P3']

export function caseTypeLabel(caseType: FcCaseType): string {
  return FC_CASE_TYPE_OPTIONS.find((item) => item.value === caseType)?.label ?? caseType
}

export interface FcExperienceCaseListResult {
  items: FcExperienceCase[]
  total: number
  page: number
  page_size: number
}

export async function fetchFcExperienceCases(
  projectId: string,
  params?: { page?: number; page_size?: number },
): Promise<FcExperienceCaseListResult> {
  const { data } = await request.get<FcExperienceCaseListResult>(
    `/fc-projects/${projectId}/experience-cases`,
    { params },
  )
  return data
}

export async function fetchAllFcExperienceCases(projectId: string): Promise<FcExperienceCase[]> {
  const pageSize = 100
  let page = 1
  const all: FcExperienceCase[] = []
  let total = 0

  do {
    const result = await fetchFcExperienceCases(projectId, { page, page_size: pageSize })
    all.push(...result.items)
    total = result.total
    page += 1
  } while (all.length < total)

  return all
}

export async function createFcExperienceCase(
  projectId: string,
  payload: FcExperienceCasePayload,
): Promise<FcExperienceCase> {
  const { data } = await request.post<FcExperienceCase>(
    `/fc-projects/${projectId}/experience-cases`,
    payload,
  )
  return data
}

export async function updateFcExperienceCase(
  projectId: string,
  caseId: string,
  payload: Partial<FcExperienceCasePayload>,
): Promise<FcExperienceCase> {
  const { data } = await request.put<FcExperienceCase>(
    `/fc-projects/${projectId}/experience-cases/${caseId}`,
    payload,
  )
  return data
}

export async function deleteFcExperienceCase(projectId: string, caseId: string): Promise<void> {
  await request.delete(`/fc-projects/${projectId}/experience-cases/${caseId}`)
}

export async function importFcExperienceCases(
  projectId: string,
  file: File,
): Promise<FcExperienceImportResult> {
  if (!file.name.toLowerCase().endsWith('.xlsx')) {
    throw new Error('仅支持 .xlsx 格式的 Excel 文件')
  }
  return postFormData<FcExperienceImportResult>(
    `/fc-projects/${projectId}/experience-cases/import`,
    file,
    'file',
    '导入经验用例失败',
  )
}

export async function downloadFcExperienceTemplate(projectId: string): Promise<void> {
  const token = getStoredToken()
  const headers: Record<string, string> = {}
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  const response = await fetch(
    `${apiBaseURL}/fc-projects/${projectId}/experience-cases/import-template`,
    { headers },
  )
  if (!response.ok) {
    throw new Error('下载模板失败')
  }

  const blob = await response.blob()
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'fc-case-template.xlsx'
  link.click()
  window.URL.revokeObjectURL(url)
}
