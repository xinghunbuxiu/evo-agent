// 统一请求封装
const API_BASE = ''

export interface ApiResponse<T = any> {
  code: number
  success: boolean
  message: string
  data: T
}

// 统一请求函数
export async function request<T>(
  url: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  const res = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    credentials: 'include',
  })

  const contentType = res.headers.get('content-type') || ''
  const data = contentType.includes('application/json')
    ? await res.json()
    : { code: res.status, success: res.ok, message: res.statusText, data: null }
  return data
}

// POST 请求
export function post<T>(url: string, body: any): Promise<ApiResponse<T>> {
  return request<T>(url, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

// GET 请求
export function get<T>(url: string): Promise<ApiResponse<T>> {
  return request<T>(url, {
    method: 'GET',
  })
}

export function put<T>(url: string, body: any): Promise<ApiResponse<T>> {
  return request<T>(url, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export function del<T>(url: string): Promise<ApiResponse<T>> {
  return request<T>(url, {
    method: 'DELETE',
  })
}
