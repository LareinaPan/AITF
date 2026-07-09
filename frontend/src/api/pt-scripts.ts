import request from './request'
import { postFormData } from './form-upload'

export interface ParsedSamplerHeader {
  name: string
  value: string
}

export interface ParsedSampler {
  key: string
  name: string
  method: string
  url: string
  headers: ParsedSamplerHeader[]
  has_variables: boolean
  thread_group_name: string | null
}

export interface ParsedThreadGroup {
  name: string
  num_threads: number | null
  ramp_time: number | null
}

export interface ParsedJmxPlan {
  thread_groups: ParsedThreadGroup[]
  samplers: ParsedSampler[]
  parse_warnings: string[]
}

export interface PtScript {
  id: string
  pt_scenario_id: string
  filename: string | null
  file_size: number | null
  parse_status: 'pending' | 'success' | 'failed'
  parse_error: string | null
  parsed_plan: ParsedJmxPlan | null
  sampler_count: number
  thread_group_count: number
  max_concurrency: number
  ramp_up_seconds: number
  stop_mode: 'request_limit' | 'duration'
  duration_seconds: number | null
  default_max_requests: number
  sampler_limits: Record<string, number> | null
  uploaded_at: string | null
  updated_at: string
}

export interface PtScriptUploadResponse {
  script: PtScript
}

export interface PtScriptConfigPayload {
  max_concurrency: number
  ramp_up_seconds: number
  stop_mode: 'request_limit' | 'duration'
  duration_seconds?: number
  default_max_requests?: number
  sampler_limits?: Record<string, number> | null
}

export async function fetchPtScript(projectId: string, scenarioId: string): Promise<PtScript> {
  const { data } = await request.get<PtScript>(
    `/pt-projects/${projectId}/scenarios/${scenarioId}/script`,
  )
  return data
}

export async function uploadPtScript(
  projectId: string,
  scenarioId: string,
  file: File,
): Promise<PtScript> {
  const response = await postFormData<PtScriptUploadResponse>(
    `/pt-projects/${projectId}/scenarios/${scenarioId}/script/upload`,
    file,
    'file',
    'JMX 上传失败',
  )
  return response.script
}

export async function updatePtScriptConfig(
  projectId: string,
  scenarioId: string,
  payload: PtScriptConfigPayload,
): Promise<PtScript> {
  const { data } = await request.put<PtScript>(
    `/pt-projects/${projectId}/scenarios/${scenarioId}/script/config`,
    payload,
  )
  return data
}
