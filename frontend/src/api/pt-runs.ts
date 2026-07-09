import { isAxiosError } from 'axios'

import request from './request'

export type PtRunStatus = 'running' | 'completed' | 'cancelled' | 'failed'

export type PtRunStopReason =
  | 'request_limit_reached'
  | 'duration_reached'
  | 'manual_cancel'
  | 'engine_error'

export interface PtRunInterfaceSummary {
  sampler_key: string
  name: string
  rt_p99_ms: number
  rt_p95_ms: number
  qps: number
  error_rate_percent: number
  total_requests: number
  failed_requests: number
}

export interface PtRunSummary {
  run_id: string
  status: string
  started_at?: string
  ended_at?: string
  stop_reason: string | null
  interfaces: PtRunInterfaceSummary[]
}

export interface PtRunListItem {
  id: string
  pt_project_id: string
  pt_scenario_id: string
  scenario_name_snapshot: string
  status: PtRunStatus
  stop_reason: PtRunStopReason | null
  triggered_by: string
  started_at: string
  ended_at: string | null
}

export interface PtRunDetail extends PtRunListItem {
  config_snapshot_json: Record<string, unknown>
  summary_json: PtRunSummary | null
  error_message: string | null
}

export interface PtRunListResponse {
  items: PtRunListItem[]
  total: number
  page: number
  page_size: number
}

export interface PtRunActionResult {
  run_id: string
  status: string
}

export interface PtRunMetricPoint {
  id: string
  sampler_key: string
  recorded_at: string
  qps: number
  avg_rt_ms: number
  rt_p95_ms: number | null
  rt_p99_ms: number | null
  error_rate_percent: number
}

export interface PtRunMetricsResponse {
  items: PtRunMetricPoint[]
}

export interface PtRunErrorLog {
  id: string
  occurred_at: string
  sampler_key: string
  sampler_name: string
  status_code: number | null
  error_type: string
  message: string
}

export interface PtRunErrorLogListResponse {
  items: PtRunErrorLog[]
  total: number | null
  page: number | null
  page_size: number | null
}

export interface FetchPtRunsParams {
  scenario_id?: string
  status?: PtRunStatus
  page?: number
  page_size?: number
}

export interface FetchPtRunMetricsParams {
  sampler_key?: string
  since?: string
}

export interface FetchPtRunErrorsParams {
  latest?: number
  page?: number
  page_size?: number
}

export const AGGREGATE_SAMPLER_KEY = '__aggregate__'

export async function fetchPtRuns(
  projectId: string,
  params?: FetchPtRunsParams,
): Promise<PtRunListResponse> {
  const { data } = await request.get<PtRunListResponse>(`/pt-projects/${projectId}/runs`, {
    params,
  })
  return data
}

export async function fetchPtRun(projectId: string, runId: string): Promise<PtRunDetail> {
  const { data } = await request.get<PtRunDetail>(`/pt-projects/${projectId}/runs/${runId}`)
  return data
}

export async function fetchPtRunMetrics(
  projectId: string,
  runId: string,
  params?: FetchPtRunMetricsParams,
): Promise<PtRunMetricsResponse> {
  const { data } = await request.get<PtRunMetricsResponse>(
    `/pt-projects/${projectId}/runs/${runId}/metrics`,
    { params },
  )
  return data
}

export async function fetchPtRunErrors(
  projectId: string,
  runId: string,
  params?: FetchPtRunErrorsParams,
): Promise<PtRunErrorLogListResponse> {
  const { data } = await request.get<PtRunErrorLogListResponse>(
    `/pt-projects/${projectId}/runs/${runId}/errors`,
    { params },
  )
  return data
}

export function ptRunDetailPath(projectId: string, runId: string): string {
  return `/pt-projects/${projectId}/runs/${runId}`
}

export async function fetchActiveRunningPtRun(
  projectId: string,
): Promise<PtRunListItem | null> {
  const response = await fetchPtRuns(projectId, { status: 'running', page_size: 1 })
  return response.items[0] ?? null
}

export interface PtRunLaunchTarget {
  runId: string
  redirected: boolean
}

export async function resolvePtRunLaunchTarget(
  projectId: string,
  scenarioId: string,
): Promise<PtRunLaunchTarget> {
  try {
    const result = await startPtRun(projectId, scenarioId)
    return { runId: String(result.run_id), redirected: false }
  } catch (error) {
    if (isAxiosError(error) && error.response?.status === 409) {
      const active = await fetchActiveRunningPtRun(projectId)
      if (active) {
        return { runId: active.id, redirected: true }
      }
    }
    throw error
  }
}

export async function startPtRun(
  projectId: string,
  scenarioId: string,
): Promise<PtRunActionResult> {
  const { data } = await request.post<PtRunActionResult>(
    `/pt-projects/${projectId}/scenarios/${scenarioId}/run`,
  )
  return data
}

export async function cancelPtRun(
  projectId: string,
  runId: string,
): Promise<PtRunActionResult> {
  const { data } = await request.post<PtRunActionResult>(
    `/pt-projects/${projectId}/runs/${runId}/cancel`,
  )
  return data
}

export function runStatusLabel(status: PtRunStatus): string {
  const labels: Record<PtRunStatus, string> = {
    running: '运行中',
    completed: '已完成',
    cancelled: '已取消',
    failed: '失败',
  }
  return labels[status]
}

export function runStatusTagType(
  status: PtRunStatus,
): 'warning' | 'success' | 'info' | 'danger' {
  const types: Record<PtRunStatus, 'warning' | 'success' | 'info' | 'danger'> = {
    running: 'warning',
    completed: 'success',
    cancelled: 'info',
    failed: 'danger',
  }
  return types[status]
}

export function stopReasonLabel(reason: PtRunStopReason | null): string {
  if (!reason) {
    return '—'
  }
  const labels: Record<PtRunStopReason, string> = {
    request_limit_reached: '请求数到达',
    duration_reached: '时长到达',
    manual_cancel: '手动取消',
    engine_error: '引擎异常',
  }
  return labels[reason]
}

export function samplerKeyLabel(key: string, fallbackName?: string): string {
  if (key === AGGREGATE_SAMPLER_KEY) {
    return '全局聚合'
  }
  return fallbackName || key
}

export function isTerminalRunStatus(status: PtRunStatus): boolean {
  return status === 'completed' || status === 'cancelled' || status === 'failed'
}
