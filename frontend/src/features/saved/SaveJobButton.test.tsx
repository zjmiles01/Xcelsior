import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { makeClient, mockFetch, routeTable } from '../../test/utils'
import { SaveJobButton } from './SaveJobButton'

afterEach(() => vi.restoreAllMocks())

const USER = { id: 1, email: 'sam@example.com' }

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="loc">{location.pathname + location.search}</div>
}

function renderButton(route: string) {
  const client = makeClient()
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/jobs/:id" element={<SaveJobButton jobId={42} />} />
          <Route path="/login" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('SaveJobButton', () => {
  it('sends an anonymous visitor to login with a redirect back', async () => {
    mockFetch(routeTable({ 'GET /api/v1/auth/me': { status: 401, json: {} } }))
    renderButton('/jobs/42')

    await userEvent.click(await screen.findByRole('button', { name: /save/i }))
    // Bounced to /login carrying the return path.
    expect(await screen.findByTestId('loc')).toHaveTextContent(
      '/login?redirect=%2Fjobs%2F42',
    )
  })

  it('reflects saved state and unsaves when already saved', async () => {
    const spy = mockFetch(
      routeTable({
        'GET /api/v1/auth/me': { status: 200, json: USER },
        'GET /api/v1/saved-jobs/ids': { status: 200, json: { job_ids: [42] } },
        'DELETE /api/v1/saved-jobs/42': { status: 204, json: null },
      }),
    )
    renderButton('/jobs/42')

    const btn = await screen.findByRole('button', { name: /saved/i })
    expect(btn).toHaveAttribute('aria-pressed', 'true')

    await userEvent.click(btn)
    expect(
      spy.mock.calls.some(
        ([url, init]) =>
          String(url).endsWith('/saved-jobs/42') && (init?.method ?? 'GET') === 'DELETE',
      ),
    ).toBe(true)
  })

  it('saves a job that is not yet saved', async () => {
    const spy = mockFetch(
      routeTable({
        'GET /api/v1/auth/me': { status: 200, json: USER },
        'GET /api/v1/saved-jobs/ids': { status: 200, json: { job_ids: [] } },
        'POST /api/v1/saved-jobs': { status: 201, json: { job_ids: [42] } },
      }),
    )
    renderButton('/jobs/42')

    const btn = await screen.findByRole('button', { name: /^☆ save$/i })
    expect(btn).toHaveAttribute('aria-pressed', 'false')

    await userEvent.click(btn)
    expect(
      spy.mock.calls.some(
        ([url, init]) =>
          String(url).endsWith('/saved-jobs') && (init?.method ?? 'GET') === 'POST',
      ),
    ).toBe(true)
  })
})
