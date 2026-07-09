import request from './request'

export interface FcProject {
  id: string
  name: string
  description: string | null
  created_by: string
  created_by_username: string
  created_at: string
}

export interface FcProjectCreatePayload {
  name: string
  description?: string | null
}

export interface FcProjectUpdatePayload {
  name?: string
  description?: string | null
}

export interface FcProjectStats {
  doc_count: number
  experience_case_count: number
  active_case_count: number
  draft_case_count: number
  batch_count: number
  last_batch_at: string | null
}

export async function fetchFcProjects(): Promise<FcProject[]> {
  const { data } = await request.get<FcProject[]>('/fc-projects')
  return data
}

export async function fetchFcProject(projectId: string): Promise<FcProject> {
  const { data } = await request.get<FcProject>(`/fc-projects/${projectId}`)
  return data
}

export async function fetchFcProjectStats(projectId: string): Promise<FcProjectStats> {
  const { data } = await request.get<FcProjectStats>(`/fc-projects/${projectId}/stats`)
  return data
}

export async function createFcProject(payload: FcProjectCreatePayload): Promise<FcProject> {
  const { data } = await request.post<FcProject>('/fc-projects', payload)
  return data
}

export async function updateFcProject(
  projectId: string,
  payload: FcProjectUpdatePayload,
): Promise<FcProject> {
  const { data } = await request.put<FcProject>(`/fc-projects/${projectId}`, payload)
  return data
}

export async function deleteFcProject(projectId: string): Promise<void> {
  await request.delete(`/fc-projects/${projectId}`)
}
