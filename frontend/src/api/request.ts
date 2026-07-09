import axios, { type AxiosInstance, isAxiosError } from 'axios'
import { FormUploadError } from '@/api/form-upload'
import { clearStoredToken, getStoredToken } from '@/utils/auth-storage'

const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

function redirectToLogin(): void {
  if (window.location.pathname.startsWith('/login') || window.location.pathname.startsWith('/register')) {
    return
  }
  const redirect = encodeURIComponent(`${window.location.pathname}${window.location.search}`)
  window.location.assign(`/login?redirect=${redirect}`)
}

export const request: AxiosInstance = axios.create({
  baseURL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

request.interceptors.request.use((config) => {
  const token = getStoredToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  if (config.data instanceof FormData) {
    if (typeof config.headers.delete === 'function') {
      config.headers.delete('Content-Type')
    } else {
      delete config.headers['Content-Type']
    }
  }
  return config
})

request.interceptors.response.use(
  (response) => response,
  (error) => {
    if (
      isAxiosError(error) &&
      error.response?.status === 401 &&
      !error.config?.url?.includes('/auth/login')
    ) {
      clearStoredToken()
      redirectToLogin()
    }
    return Promise.reject(error)
  },
)

export function getApiErrorMessage(error: unknown, fallback = '请求失败，请稍后重试'): string {
  if (error instanceof FormUploadError) {
    return error.message
  }

  if (error instanceof Error && error.message) {
    return error.message
  }

  if (!isAxiosError(error)) {
    return fallback
  }

  if (error.code === 'ECONNABORTED') {
    return '请求超时，请稍后重试'
  }

  if (!error.response) {
    return '无法连接后端服务，请确认 API 已启动'
  }

  const status = error.response.status
  if (status === 403) {
    return '无权限访问，请重新登录'
  }
  if (status >= 500) {
    return '服务器异常，请稍后重试'
  }

  const detail = error.response.data?.detail
  if (typeof detail === 'string') {
    return detail
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0]
    if (typeof first?.msg === 'string') {
      return first.msg
    }
  }

  return fallback
}

export default request
