import request from './request'
import type { TestCase } from './testCases'

export interface ApiEndpoint {
  id: string
  project_id: string
  method: string
  path: string
  summary: string | null
  description: string | null
  parameters_json: Record<string, unknown>[]
  request_body_json: Record<string, unknown> | null
  responses_json: Record<string, unknown>
  created_at: string
  test_case_count?: number
}

export interface ApiEndpointListResult {
  items: ApiEndpoint[]
  total: number
  page: number
  page_size: number
}

export interface OpenAPIUploadResult {
  filename: string
  created: number
  updated: number
  total: number
}

export interface AIGeneratePayload {
  positive_count: number
  boundary_count: number
  exception_count: number
  auth_count: number
}

export interface AIGenerateResult {
  cases: TestCase[]
  requested_count: number
  rejected_count: number
  raw_count: number
}

export const DEFAULT_AI_GENERATE_COUNTS: AIGeneratePayload = {
  positive_count: 2,
  boundary_count: 1,
  exception_count: 1,
  auth_count: 0,
}

export async function fetchApiEndpoints(
  projectId: string,
  page = 1,
  pageSize = 20,
): Promise<ApiEndpointListResult> {
  const { data } = await request.get<ApiEndpointListResult>(`/projects/${projectId}/apis`, {
    params: { page, page_size: pageSize },
  })
  return data
}

export async function fetchAllApiEndpoints(projectId: string): Promise<ApiEndpoint[]> {
  const pageSize = 100
  const firstPage = await fetchApiEndpoints(projectId, 1, pageSize)
  const endpoints = [...firstPage.items]

  if (firstPage.total <= pageSize) {
    return endpoints
  }

  const totalPages = Math.ceil(firstPage.total / pageSize)
  const remainingPages = await Promise.all(
    Array.from({ length: totalPages - 1 }, (_, index) =>
      fetchApiEndpoints(projectId, index + 2, pageSize),
    ),
  )

  for (const page of remainingPages) {
    endpoints.push(...page.items)
  }

  return endpoints
}

export async function fetchApiEndpoint(projectId: string, apiId: string): Promise<ApiEndpoint> {
  const { data } = await request.get<ApiEndpoint>(`/projects/${projectId}/apis/${apiId}`)
  return data
}

export async function deleteApiEndpoint(projectId: string, apiId: string): Promise<void> {
  await request.delete(`/projects/${projectId}/apis/${apiId}`)
}

export async function uploadOpenApi(projectId: string, file: File): Promise<OpenAPIUploadResult> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await request.post<OpenAPIUploadResult>(
    `/projects/${projectId}/openapi/upload`,
    formData,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
    },
  )
  return data
}

export async function generateAiTestCases(
  projectId: string,
  apiId: string,
  payload: AIGeneratePayload,
): Promise<AIGenerateResult> {
  const { data } = await request.post<AIGenerateResult>(
    `/projects/${projectId}/apis/${apiId}/ai-generate`,
    payload,
    { timeout: 120000 },
  )
  return data
}

export function formatJson(value: unknown): string {
  if (value === null || value === undefined) {
    return ''
  }
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

export function methodTagType(method: string): 'success' | 'warning' | 'danger' | 'info' | '' {
  switch (method.toUpperCase()) {
    case 'GET':
      return 'success'
    case 'POST':
      return ''
    case 'PUT':
    case 'PATCH':
      return 'warning'
    case 'DELETE':
      return 'danger'
    default:
      return 'info'
  }
}

export function getTotalGenerateCount(payload: AIGeneratePayload): number {
  return (
    payload.positive_count
    + payload.boundary_count
    + payload.exception_count
    + payload.auth_count
  )
}
