import request from './request'

export interface HealthResponse {
  status: string
  service?: string
}

export async function fetchApiHealth(): Promise<HealthResponse> {
  const { data } = await request.get<HealthResponse>('/health')
  return data
}
