import request from './request'

export interface Environment {
  id: string
  name: string
  is_default: boolean
}

export interface EnvironmentVariable {
  id: string
  key: string
  value: string
  is_secret: boolean
}

export interface EnvironmentVariablePayload {
  key: string
  value: string
  is_secret: boolean
}

export interface EnvironmentCreatePayload {
  name: string
  is_default?: boolean
}

export async function fetchEnvironments(): Promise<Environment[]> {
  const { data } = await request.get<Environment[]>('/environments')
  return data
}

export async function createEnvironment(payload: EnvironmentCreatePayload): Promise<Environment> {
  const { data } = await request.post<Environment>('/environments', payload)
  return data
}

export async function updateEnvironment(
  environmentId: string,
  payload: Partial<EnvironmentCreatePayload>,
): Promise<Environment> {
  const { data } = await request.put<Environment>(`/environments/${environmentId}`, payload)
  return data
}

export async function deleteEnvironment(environmentId: string): Promise<void> {
  await request.delete(`/environments/${environmentId}`)
}

export async function fetchEnvironmentVariables(
  environmentId: string,
): Promise<EnvironmentVariable[]> {
  const { data } = await request.get<EnvironmentVariable[]>(
    `/environments/${environmentId}/variables`,
  )
  return data
}

export async function saveEnvironmentVariables(
  environmentId: string,
  variables: EnvironmentVariablePayload[],
): Promise<EnvironmentVariable[]> {
  const { data } = await request.put<EnvironmentVariable[]>(
    `/environments/${environmentId}/variables`,
    { variables },
  )
  return data
}
