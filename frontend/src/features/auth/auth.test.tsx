import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { makeClient, mockFetch, routeTable } from '../../test/utils'
import { LoginPage } from './AuthPage'
import { RequireAuth } from './RequireAuth'

afterEach(() => vi.restoreAllMocks())

const USER = { id: 1, email: 'sam@example.com' }

function Protected() {
  return <p>secret dashboard</p>
}

function LoginStub() {
  return <p>login screen</p>
}

/** Render a tiny app with a protected route and a login route, at `route`. */
function renderApp(route: string) {
  const client = makeClient()
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route
            path="/secret"
            element={
              <RequireAuth>
                <Protected />
              </RequireAuth>
            }
          />
          <Route path="/login" element={<LoginStub />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('RequireAuth', () => {
  it('renders the protected content for an authenticated user', async () => {
    mockFetch(routeTable({ 'GET /api/v1/auth/me': { status: 200, json: USER } }))
    renderApp('/secret')
    expect(await screen.findByText('secret dashboard')).toBeInTheDocument()
  })

  it('redirects an anonymous visitor to the login screen', async () => {
    mockFetch(routeTable({ 'GET /api/v1/auth/me': { status: 401, json: {} } }))
    renderApp('/secret')
    expect(await screen.findByText('login screen')).toBeInTheDocument()
    expect(screen.queryByText('secret dashboard')).not.toBeInTheDocument()
  })
})

describe('LoginPage', () => {
  it('logs in and redirects to the target from the redirect param', async () => {
    const spy = mockFetch(
      routeTable({
        'GET /api/v1/auth/me': { status: 401, json: {} },
        'POST /api/v1/auth/login': { status: 200, json: USER },
      }),
    )
    const client = makeClient()
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/login?redirect=%2Fsaved']}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/saved" element={<p>saved jobs page</p>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    await userEvent.type(screen.getByLabelText('Email'), 'sam@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'a-good-password')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

    // Landed on the redirect target after a successful login.
    expect(await screen.findByText('saved jobs page')).toBeInTheDocument()
    const loginCall = spy.mock.calls.find(([url]) => String(url).endsWith('/auth/login'))
    expect(loginCall).toBeTruthy()
  })

  it('shows the server error on invalid credentials', async () => {
    mockFetch(
      routeTable({
        'GET /api/v1/auth/me': { status: 401, json: {} },
        'POST /api/v1/auth/login': { status: 401, json: { detail: 'Invalid email or password' } },
      }),
    )
    const client = makeClient()
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/login']}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    await userEvent.type(screen.getByLabelText('Email'), 'sam@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'wrong-password')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

    await waitFor(() =>
      expect(screen.getByText('Invalid email or password')).toBeInTheDocument(),
    )
  })
})
