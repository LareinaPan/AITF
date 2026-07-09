import request from './request'

import type { FcTestCase } from './fc-test-cases'

export type FcGenerationBatchStatus =
  | 'pending'
  | 'generating'
  | 'reviewing'
  | 'awaiting_review'
  | 'completed'
  | 'failed'

export interface FcGenerationBatch {
  id: string
  fc_project_id: string
  requirement_doc_id: string
  experience_case_ids: string[]
  status: FcGenerationBatchStatus
  coverage_score: number | null
  review_report_json: Record<string, unknown> | null
  user_feedback: string | null
  internal_retry_count: number
  parent_batch_id: string | null
  triggered_by: string
  triggered_by_username: string
  error_message: string | null
  created_at: string
  completed_at: string | null
  case_count: number
}

export interface FcGeneratePayload {
  requirement_doc_id: string
  experience_case_ids?: string[]
  user_feedback?: string | null
  parent_batch_id?: string | null
}

export interface FcGenerateResult {
  batch_id: string
  status: string
}

export interface FcReviewReport {
  coverage_score?: number
  dimension_scores?: Record<string, number>
  feature_checklist?: Array<{ feature: string; covered: boolean; case_count: number }>
  gaps?: string[]
  suggestions?: string[]
  passed?: boolean
}

export interface FcBatchConfirmResult {
  confirmed_count: number
  batch_status: string
}

export interface FcBatchRejectResult {
  batch_id: string
  status: string
  parent_batch_id: string
}

const TERMINAL_STATUSES: FcGenerationBatchStatus[] = [
  'awaiting_review',
  'completed',
  'failed',
]

export function isTerminalBatchStatus(status: FcGenerationBatchStatus): boolean {
  return TERMINAL_STATUSES.includes(status)
}

export function batchStatusLabel(status: FcGenerationBatchStatus): string {
  switch (status) {
    case 'pending':
      return '排队中'
    case 'generating':
      return 'AI 生成用例中'
    case 'reviewing':
      return 'AI 审查覆盖度中'
    case 'awaiting_review':
      return '等待人工复查'
    case 'completed':
      return '已完成'
    case 'failed':
      return '生成失败'
    default:
      return status
  }
}

export function batchStatusProgress(status: FcGenerationBatchStatus): number {
  switch (status) {
    case 'pending':
      return 10
    case 'generating':
      return 45
    case 'reviewing':
      return 80
    case 'awaiting_review':
    case 'completed':
      return 100
    case 'failed':
      return 100
    default:
      return 0
  }
}

export function batchStatusTagType(
  status: FcGenerationBatchStatus,
): 'success' | 'warning' | 'danger' | 'info' {
  switch (status) {
    case 'awaiting_review':
    case 'completed':
      return 'success'
    case 'failed':
      return 'danger'
    case 'generating':
    case 'reviewing':
      return 'warning'
    default:
      return 'info'
  }
}

export async function startFcGeneration(
  projectId: string,
  payload: FcGeneratePayload,
): Promise<FcGenerateResult> {
  const { data } = await request.post<FcGenerateResult>(
    `/fc-projects/${projectId}/generate`,
    payload,
  )
  return data
}

export async function fetchFcGenerationBatch(
  projectId: string,
  batchId: string,
): Promise<FcGenerationBatch> {
  const { data } = await request.get<FcGenerationBatch>(
    `/fc-projects/${projectId}/batches/${batchId}`,
  )
  return data
}

export async function fetchFcGenerationBatches(projectId: string): Promise<FcGenerationBatch[]> {
  const { data } = await request.get<FcGenerationBatch[]>(`/fc-projects/${projectId}/batches`)
  return data
}

export async function pollFcGenerationBatch(
  projectId: string,
  batchId: string,
  options?: {
    intervalMs?: number
    onUpdate?: (batch: FcGenerationBatch) => void
    signal?: AbortSignal
  },
): Promise<FcGenerationBatch> {
  const intervalMs = options?.intervalMs ?? 2000

  return new Promise((resolve, reject) => {
    let timer: ReturnType<typeof setTimeout> | null = null

    const cleanup = (): void => {
      if (timer !== null) {
        clearTimeout(timer)
        timer = null
      }
      options?.signal?.removeEventListener('abort', onAbort)
    }

    const onAbort = (): void => {
      cleanup()
      reject(new DOMException('Polling aborted', 'AbortError'))
    }

    if (options?.signal?.aborted) {
      onAbort()
      return
    }
    options?.signal?.addEventListener('abort', onAbort)

    const tick = async (): Promise<void> => {
      try {
        const batch = await fetchFcGenerationBatch(projectId, batchId)
        options?.onUpdate?.(batch)
        if (isTerminalBatchStatus(batch.status)) {
          cleanup()
          resolve(batch)
          return
        }
        timer = setTimeout(() => {
          void tick()
        }, intervalMs)
      } catch (error) {
        cleanup()
        reject(error)
      }
    }

    void tick()
  })
}

export async function fetchBatchDraftCases(
  projectId: string,
  batchId: string,
): Promise<FcTestCase[]> {
  const { data } = await request.get<FcTestCase[]>(
    `/fc-projects/${projectId}/batches/${batchId}/cases`,
  )
  return data
}

export async function confirmBatchCases(
  projectId: string,
  batchId: string,
  caseIds: string[] = [],
): Promise<FcBatchConfirmResult> {
  const { data } = await request.post<FcBatchConfirmResult>(
    `/fc-projects/${projectId}/batches/${batchId}/confirm`,
    { case_ids: caseIds },
  )
  return data
}

export async function rejectBatchAndRegenerate(
  projectId: string,
  batchId: string,
  feedback: string,
): Promise<FcBatchRejectResult> {
  const { data } = await request.post<FcBatchRejectResult>(
    `/fc-projects/${projectId}/batches/${batchId}/reject`,
    { feedback },
  )
  return data
}
