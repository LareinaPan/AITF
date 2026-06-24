import request from './request'

export interface ProjectStatsItem {
  project_id: string
  name: string
  apis: number
  cases: number
}

export interface DashboardStats {
  total_apis: number
  total_cases: number
  by_project: ProjectStatsItem[]
}

export async function fetchDashboardStats(): Promise<DashboardStats> {
  const { data } = await request.get<DashboardStats>('/dashboard/stats')
  return data
}
