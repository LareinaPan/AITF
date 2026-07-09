import request from './request'

export interface PtScenario {
  id: string
  pt_project_id: string
  name: string
  description: string | null
  script_id: string
  parse_status: 'pending' | 'success' | 'failed'
  last_run_status: string | null
  last_run_at: string | null
  created_at: string
  updated_at: string
}

export interface PtScenarioCreatePayload {
  name: string
  description?: string | null
}

export interface PtScenarioUpdatePayload {
  name?: string
  description?: string | null
}

export async function fetchPtScenarios(projectId: string): Promise<PtScenario[]> {
  const { data } = await request.get<PtScenario[]>(`/pt-projects/${projectId}/scenarios`)
  return data
}

export async function fetchPtScenario(projectId: string, scenarioId: string): Promise<PtScenario> {
  const { data } = await request.get<PtScenario>(
    `/pt-projects/${projectId}/scenarios/${scenarioId}`,
  )
  return data
}

export async function createPtScenario(
  projectId: string,
  payload: PtScenarioCreatePayload,
): Promise<PtScenario> {
  const { data } = await request.post<PtScenario>(`/pt-projects/${projectId}/scenarios`, payload)
  return data
}

export async function updatePtScenario(
  projectId: string,
  scenarioId: string,
  payload: PtScenarioUpdatePayload,
): Promise<PtScenario> {
  const { data } = await request.put<PtScenario>(
    `/pt-projects/${projectId}/scenarios/${scenarioId}`,
    payload,
  )
  return data
}

export async function deletePtScenario(projectId: string, scenarioId: string): Promise<void> {
  await request.delete(`/pt-projects/${projectId}/scenarios/${scenarioId}`)
}

export function parseStatusLabel(status: PtScenario['parse_status']): string {
  const labels: Record<PtScenario['parse_status'], string> = {
    pending: '待上传',
    success: '已解析',
    failed: '解析失败',
  }
  return labels[status]
}

export function parseStatusTagType(
  status: PtScenario['parse_status'],
): 'info' | 'success' | 'danger' {
  const types: Record<PtScenario['parse_status'], 'info' | 'success' | 'danger'> = {
    pending: 'info',
    success: 'success',
    failed: 'danger',
  }
  return types[status]
}
