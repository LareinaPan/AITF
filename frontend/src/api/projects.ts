import request from './request'

export interface Project {
  id: string
  name: string
  description: string | null
  feishu_webhook_url: string | null
  created_by: string
  created_by_username: string
  created_at: string
}

export interface ProjectCreatePayload {
  name: string
  description?: string | null
  feishu_webhook_url?: string | null
}

export interface ProjectUpdatePayload {
  name?: string
  description?: string | null
  feishu_webhook_url?: string | null
}

export async function fetchProjects(): Promise<Project[]> {
  const { data } = await request.get<Project[]>('/projects')
  return data
}

export async function fetchProject(projectId: string): Promise<Project> {
  const { data } = await request.get<Project>(`/projects/${projectId}`)
  return data
}

export async function createProject(payload: ProjectCreatePayload): Promise<Project> {
  const { data } = await request.post<Project>('/projects', payload)
  return data
}

export async function updateProject(
  projectId: string,
  payload: ProjectUpdatePayload,
): Promise<Project> {
  const { data } = await request.put<Project>(`/projects/${projectId}`, payload)
  return data
}

export async function deleteProject(projectId: string): Promise<void> {
  await request.delete(`/projects/${projectId}`)
}
