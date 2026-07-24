import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, apiGet, apiSend, isAuthError } from './client'

afterEach(() => vi.restoreAllMocks())

function fetchReturning(status: number, body: unknown) {
  return vi.fn(async () => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  })) as unknown as typeof fetch
}

describe('apiGet', () => {
  it('sends cookies same-origin and returns JSON on success', async () => {
    const spy = fetchReturning(200, { hello: 'world' })
    global.fetch = spy
    const data = await apiGet<{ hello: string }>('/meta')
    expect(data).toEqual({ hello: 'world' })
    const [, init] = (spy as unknown as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(init.credentials).toBe('same-origin')
  })

  it('throws a typed ApiError carrying the status on failure', async () => {
    global.fetch = fetchReturning(401, {})
    await expect(apiGet('/profiles')).rejects.toMatchObject({ status: 401 })
  })
})

describe('apiSend', () => {
  it('returns undefined for a 204 with no body', async () => {
    global.fetch = fetchReturning(204, null)
    await expect(apiSend('DELETE', '/saved-jobs/1')).resolves.toBeUndefined()
  })

  it('surfaces the server problem-details detail as the error message', async () => {
    global.fetch = fetchReturning(409, { detail: 'An account with this email already exists' })
    await expect(apiSend('POST', '/auth/signup', { email: 'x', password: 'y' })).rejects.toThrow(
      'An account with this email already exists',
    )
  })

  it('sets a JSON content-type for object bodies', async () => {
    const spy = fetchReturning(200, {})
    global.fetch = spy
    await apiSend('POST', '/auth/login', { email: 'a', password: 'b' })
    const [, init] = (spy as unknown as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(init.credentials).toBe('same-origin')
  })
})

describe('isAuthError', () => {
  it('is true for 401 and 403 ApiErrors only', () => {
    expect(isAuthError(new ApiError(401, 'x'))).toBe(true)
    expect(isAuthError(new ApiError(403, 'x'))).toBe(true)
    expect(isAuthError(new ApiError(404, 'x'))).toBe(false)
    expect(isAuthError(new Error('nope'))).toBe(false)
  })
})
