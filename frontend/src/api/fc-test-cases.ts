import request from './request'

import type { FcCaseType, FcPriority } from './fc-experience-cases'

export interface FcTestCase {
  id: string
  fc_project_id: string
  requirement_doc_id: string | null
  generation_batch_id: string | null
  case_no: string
  module: string
  title: string
  preconditions: string | null
  steps: string
  expected_result: string
  priority: FcPriority
  case_type: FcCaseType
  status: 'draft' | 'active'
  created_at: string
  updated_at: string
}

export interface FcTestCaseUpdatePayload {
  case_no?: string
  module?: string
  title?: string
  preconditions?: string | null
  steps?: string
  expected_result?: string
  priority?: FcPriority
  case_type?: FcCaseType
  status?: 'draft' | 'active'
}

export async function updateFcTestCase(
  projectId: string,
  caseId: string,
  payload: FcTestCaseUpdatePayload,
): Promise<FcTestCase> {
  const { data } = await request.put<FcTestCase>(
    `/fc-projects/${projectId}/cases/${caseId}`,
    payload,
  )
  return data
}

export async function deleteFcTestCase(projectId: string, caseId: string): Promise<void> {
  await request.delete(`/fc-projects/${projectId}/cases/${caseId}`)
}

export async function batchDeleteFcTestCases(
  projectId: string,
  caseIds: string[],
): Promise<number> {
  const { data } = await request.post<{ deleted_count: number }>(
    `/fc-projects/${projectId}/cases/batch-delete`,
    { case_ids: caseIds },
  )
  return data.deleted_count
}

export interface FcTestCaseListParams {
  status?: 'draft' | 'active'
  module?: string
  case_type?: FcCaseType
  generation_batch_id?: string
  no_batch?: boolean
  page?: number
  page_size?: number
}

export interface FcTestCaseListResult {
  items: FcTestCase[]
  total: number
  page: number
  page_size: number
}

export interface FcTestCaseFilterOptions {
  modules: string[]
  generation_batch_ids: string[]
  has_no_batch: boolean
}

export async function fetchFcTestCaseFilterOptions(
  projectId: string,
  status: 'draft' | 'active' = 'active',
): Promise<FcTestCaseFilterOptions> {
  const { data } = await request.get<FcTestCaseFilterOptions>(
    `/fc-projects/${projectId}/cases/filter-options`,
    { params: { status } },
  )
  return data
}

export async function fetchFcTestCases(
  projectId: string,
  params?: FcTestCaseListParams,
): Promise<FcTestCaseListResult> {
  const { data } = await request.get<FcTestCaseListResult>(`/fc-projects/${projectId}/cases`, {
    params,
  })
  return data
}
