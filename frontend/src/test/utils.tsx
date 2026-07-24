import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

/** A QueryClient with retries off, so a mocked 4xx surfaces immediately
 * instead of being retried into a timeout. */
export function makeClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })
}

export function renderWithProviders(
  ui: ReactElement,
  { route = '/', client = makeClient() }: { route?: string; client?: QueryClient } = {},
) {
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
      </QueryClientProvider>,
    ),
  }
}

export type FakeResponse = { status?: number; json?: unknown }
export type FetchHandler = (url: string, init?: RequestInit) => FakeResponse

/** Install a fetch mock driven by a handler that maps "METHOD /path" to a
 * response. Returns the underlying spy so tests can assert on calls. */
export function mockFetch(handler: FetchHandler) {
  const spy = vi.fn(async (url: string | URL, init?: RequestInit) => {
    const { status = 200, json = {} } = handler(String(url), init)
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => json,
    } as Response
  })
  global.fetch = spy as unknown as typeof fetch
  return spy
}

/** Convenience for a route table keyed by "METHOD /api/v1/path". */
export function routeTable(routes: Record<string, FakeResponse>): FetchHandler {
  return (url, init) => {
    const method = (init?.method ?? 'GET').toUpperCase()
    const path = url.replace(/^.*\/api\/v1/, '/api/v1').split('?')[0]
    const key = `${method} ${path}`
    return routes[key] ?? { status: 404, json: { detail: `no mock for ${key}` } }
  }
}
