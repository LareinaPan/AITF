import request from './request'

export interface PtProject {
  id: string
  name: string
  description: string | null
  created_by: string
  created_by_username: string
  created_at: string
}

export interface PtProjectCreatePayload {
  name: string
  description?: string | null
}

export interface PtProjectUpdatePayload {
  name?: string
  description?: string | null
}

export interface PtProjectStats {
  scenario_count: number
  run_count: number
  last_run_at: string | null
  last_run_status: string | null
}

export async function fetchPtProjects(): Promise<PtProject[]> {
  const { data } = await request.get<PtProject[]>('/pt-projects')
  return data
}

export async function fetchPtProject(projectId: string): Promise<PtProject> {
  const { data } = await request.get<PtProject>(`/pt-projects/${projectId}`)
  return data
}

export async function fetchPtProjectStats(projectId: string): Promise<PtProjectStats> {
  const { data } = await request.get<PtProjectStats>(`/pt-projects/${projectId}/stats`)
  return data
}

export async function createPtProject(payload: PtProjectCreatePayload): Promise<PtProject> {
  const { data } = await request.post<PtProject>('/pt-projects', payload)
  return data
}

export async function updatePtProject(
  projectId: string,
  payload: PtProjectUpdatePayload,
): Promise<PtProject> {
  const { data } = await request.put<PtProject>(`/pt-projects/${projectId}`, payload)
  return data
}

export async function deletePtProject(projectId: string): Promise<void> {
  await request.delete(`/pt-projects/${projectId}`)
}
