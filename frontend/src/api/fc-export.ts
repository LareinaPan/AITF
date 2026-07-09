import { getStoredToken } from '@/utils/auth-storage'

import type { FcCaseType } from './fc-experience-cases'

const apiBaseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

export interface FcExportFilters {
  status?: 'active' | 'draft'
  module?: string
  case_type?: FcCaseType
  generation_batch_id?: string
  no_batch?: boolean
}

function buildExportQuery(filters?: FcExportFilters): string {
  const params = new URLSearchParams()
  if (filters?.status) {
    params.set('status', filters.status)
  }
  if (filters?.module) {
    params.set('module', filters.module)
  }
  if (filters?.case_type) {
    params.set('case_type', filters.case_type)
  }
  if (filters?.generation_batch_id) {
    params.set('generation_batch_id', filters.generation_batch_id)
  }
  if (filters?.no_batch) {
    params.set('no_batch', 'true')
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

function parseDownloadFilename(disposition: string, fallback: string): string {
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1])
    } catch {
      // ignore malformed UTF-8 filename*
    }
  }
  const asciiMatch = disposition.match(/filename="([^"]+)"/)
  return asciiMatch?.[1] ?? fallback
}

async function downloadExportFile(
  projectId: string,
  format: 'excel' | 'xmind',
  filters: FcExportFilters | undefined,
  fallbackFilename: string,
): Promise<void> {
  const token = getStoredToken()
  const headers: Record<string, string> = {}
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  let response: Response
  try {
    response = await fetch(
      `${apiBaseURL}/fc-projects/${projectId}/export/${format}${buildExportQuery(filters)}`,
      { headers },
    )
  } catch {
    throw new Error('无法连接后端服务，请确认 API 已启动')
  }
  if (!response.ok) {
    let message = '导出失败'
    try {
      const payload = (await response.json()) as { detail?: string }
      if (payload.detail) {
        message = payload.detail
      }
    } catch {
      // ignore parse errors
    }
    throw new Error(message)
  }

  const disposition = response.headers.get('content-disposition') ?? ''
  const filename = parseDownloadFilename(disposition, fallbackFilename)

  const blob = await response.blob()
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  window.URL.revokeObjectURL(url)
}

export async function exportFcCasesExcel(
  projectId: string,
  filters?: FcExportFilters,
): Promise<void> {
  await downloadExportFile(projectId, 'excel', filters, 'fc-cases.xlsx')
}

export async function exportFcCasesXmind(
  projectId: string,
  filters?: FcExportFilters,
): Promise<void> {
  await downloadExportFile(projectId, 'xmind', filters, 'fc-cases.xmind')
}
