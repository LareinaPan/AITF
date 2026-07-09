import { getStoredToken } from '@/utils/auth-storage'

const apiBaseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

export class FormUploadError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'FormUploadError'
    this.status = status
  }
}

function extractErrorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== 'object') {
    return fallback
  }

  const detail = (payload as { detail?: unknown }).detail
  if (typeof detail === 'string') {
    return detail
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: unknown }
    if (typeof first?.msg === 'string') {
      return first.msg
    }
  }

  return fallback
}

export async function postFormData<T>(
  path: string,
  file: File,
  fieldName = 'file',
  fallbackMessage = '上传失败，请稍后重试',
): Promise<T> {
  const formData = new FormData()
  formData.append(fieldName, file, file.name)

  const token = getStoredToken()
  const headers: Record<string, string> = {}
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  let response: Response
  try {
    response = await fetch(`${apiBaseURL}${path}`, {
      method: 'POST',
      headers,
      body: formData,
    })
  } catch {
    throw new FormUploadError('无法连接后端服务，请确认 API 已启动', 0)
  }

  let payload: unknown = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  if (!response.ok) {
    throw new FormUploadError(
      extractErrorMessage(payload, fallbackMessage),
      response.status,
    )
  }

  return payload as T
}
