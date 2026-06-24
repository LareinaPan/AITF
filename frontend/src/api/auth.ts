import request from './request'

export interface User {
  id: string
  username: string
}

export interface LoginPayload {
  username: string
  password: string
}

export interface RegisterPayload {
  username: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}

export async function login(payload: LoginPayload): Promise<TokenResponse> {
  const { data } = await request.post<TokenResponse>('/auth/login', payload)
  return data
}

export async function register(payload: RegisterPayload): Promise<User> {
  const { data } = await request.post<User>('/auth/register', payload)
  return data
}

export async function fetchCurrentUser(): Promise<User> {
  const { data } = await request.get<User>('/auth/me')
  return data
}
