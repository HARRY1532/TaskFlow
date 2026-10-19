export const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api'

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('taskflow_token')
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      ...(init.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  })
  if (response.status === 204) return undefined as T
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = body.detail
    throw new ApiError(response.status, typeof detail === 'string' ? detail : '请求失败，请检查输入')
  }
  return body as T
}

export function json(method: string, body: unknown): RequestInit {
  return { method, body: JSON.stringify(body) }
}
