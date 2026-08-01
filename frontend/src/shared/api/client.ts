// Typed API client using OpenAPI-generated types and same-origin session cookies.
const FETCH_OPTS: RequestInit = { credentials: 'same-origin' }

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** True for auth failures (no/invalid session) — 401 or 403. */
export function isAuthError(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 401 || error.status === 403)
}

export async function apiGet<T>(path: string, params?: URLSearchParams): Promise<T> {
  const query = params && params.size > 0 ? `?${params.toString()}` : ''
  const response = await fetch(`/api/v1${path}${query}`, FETCH_OPTS)
  if (!response.ok) {
    throw new ApiError(response.status, `GET ${path} failed with ${response.status}`)
  }
  return response.json() as Promise<T>
}

/** Sends a mutating API request and surfaces server error details. */

export async function apiSend<T>(
  method: 'POST' | 'PUT' | 'DELETE',
  path: string,
  body?: object | FormData,
): Promise<T> {
  const isForm = body instanceof FormData
  const headers: Record<string, string> = {}
  // Let the browser set multipart boundaries; only JSON bodies get a type.
  if (!isForm && body !== undefined) headers['Content-Type'] = 'application/json'
  const response = await fetch(`/api/v1${path}`, {
    ...FETCH_OPTS,
    method,
    body: isForm ? body : body !== undefined ? JSON.stringify(body) : undefined,
    headers,
  })
  if (!response.ok) {
    let detail = `${method} ${path} failed with ${response.status}`
    try {
      const problem = (await response.json()) as { detail?: string; title?: string }
      // Prefer the server-provided error message over a generic request error.

      const message = problem.detail ?? problem.title
      if (typeof message === 'string') detail = message
    } catch {
      // non-JSON error body: keep the generic message
    }
    throw new ApiError(response.status, detail)
  }
  return response.status === 204 ? (undefined as T) : (response.json() as Promise<T>)
}
