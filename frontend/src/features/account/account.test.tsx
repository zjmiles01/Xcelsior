import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { makeClient, mockFetch, routeTable } from '../../test/utils'
import { LoginPage } from '../auth/AuthPage'
import { CURRENT_USER_KEY, useCurrentUser } from '../auth/api'
import { AccountPage } from './AccountPage'

afterEach(() => vi.restoreAllMocks())

const USER = { id: 1, email: 'sam@example.com' }

/** Stands in for the header, which observes the current user on every page.
 * Keeping an observer mounted across the redirect is what makes "the app
 * now believes you are signed out" an assertable, user-visible fact. */
function IdentityProbe() {
  const { data: user, isPending } = useCurrentUser()
  return <span data-testid="identity">{isPending ? 'checking' : (user?.email ?? 'anonymous')}</span>
}

/** The account page with a real /login route to land on, so the redirect
 * after deletion is observable rather than mocked away. */
function renderAccount() {
  const client = makeClient()
  const view = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/account']}>
        <IdentityProbe />
        <Routes>
          <Route path="/account" element={<AccountPage />} />
          <Route path="/login" element={<LoginPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...view, client }
}

const deleteCalls = (spy: ReturnType<typeof mockFetch>) =>
  spy.mock.calls.filter(
    ([url, init]) => String(url).endsWith('/account') && init?.method === 'DELETE',
  )

async function openDialog() {
  await userEvent.click(await screen.findByRole('button', { name: 'Delete account' }))
  return screen.getByRole('dialog')
}

const confirmButton = () => screen.getByRole('button', { name: 'Delete my account' })

describe('AccountPage danger zone', () => {
  it('opens the confirmation dialog from the danger zone', async () => {
    mockFetch(routeTable({ 'GET /api/v1/auth/me': { status: 200, json: USER } }))
    renderAccount()

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    const dialog = await openDialog()

    expect(dialog).toHaveTextContent('Delete your account?')
    // The dialog names the account and says plainly that it is final.
    expect(dialog).toHaveTextContent(USER.email)
    expect(dialog).toHaveTextContent(/cannot be undone/i)
  })

  it('keeps the final button disabled until DELETE is typed exactly', async () => {
    const spy = mockFetch(routeTable({ 'GET /api/v1/auth/me': { status: 200, json: USER } }))
    renderAccount()
    await openDialog()

    expect(confirmButton()).toBeDisabled()

    const input = screen.getByLabelText(/type/i)
    await userEvent.type(input, 'delete')
    expect(confirmButton()).toBeDisabled() // case matters

    await userEvent.clear(input)
    await userEvent.type(input, 'DELETE ME')
    expect(confirmButton()).toBeDisabled() // near enough is not enough

    await userEvent.clear(input)
    await userEvent.type(input, 'DELETE')
    expect(confirmButton()).toBeEnabled()

    // Nothing reached the server while the gate was closed.
    expect(deleteCalls(spy)).toHaveLength(0)
  })

  it('closes without deleting when cancelled', async () => {
    const spy = mockFetch(routeTable({ 'GET /api/v1/auth/me': { status: 200, json: USER } }))
    renderAccount()
    await openDialog()

    await userEvent.type(screen.getByLabelText(/type/i), 'DELETE')
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(deleteCalls(spy)).toHaveLength(0)
  })

  it('sends one request only, however many times the button is pressed', async () => {
    // A delete held open in flight — the window in which an impatient second
    // click would otherwise delete twice (or race the redirect).
    let release: () => void = () => {}
    const inFlight = new Promise<void>((resolve) => {
      release = resolve
    })
    const sent: string[] = []
    global.fetch = vi.fn(async (url: string | URL, init?: RequestInit) => {
      if (String(url).endsWith('/account') && init?.method === 'DELETE') {
        sent.push(String(url))
        await inFlight
        return { ok: true, status: 204, json: async () => null } as Response
      }
      return { ok: true, status: 200, json: async () => USER } as Response
    }) as unknown as typeof fetch

    renderAccount()
    await openDialog()
    await userEvent.type(screen.getByLabelText(/type/i), 'DELETE')
    await userEvent.click(confirmButton())

    // While the request is open the control is inert and says so.
    const pendingButton = await screen.findByRole('button', { name: 'Deleting…' })
    expect(pendingButton).toBeDisabled()
    await userEvent.click(pendingButton)
    expect(sent).toHaveLength(1)

    release()
    expect(await screen.findByText(/have been deleted/i)).toBeInTheDocument()
    expect(sent).toHaveLength(1)
  })

  it('clears auth state and redirects to sign-in after a successful delete', async () => {
    // The server-side truth after a delete: the session is gone, so /auth/me
    // stops recognising the caller. Mocking it any other way would let the
    // test pass on a client that never actually dropped the identity.
    let deleted = false
    mockFetch((url, init) => {
      const method = init?.method ?? 'GET'
      if (url.endsWith('/account') && method === 'DELETE') {
        deleted = true
        return { status: 204, json: null }
      }
      if (url.includes('/auth/me')) {
        return deleted ? { status: 401, json: {} } : { status: 200, json: USER }
      }
      return { status: 404, json: {} }
    })
    const { client } = renderAccount()
    // Cached data belonging to the account that is about to disappear.
    client.setQueryData(['profiles'], { items: [{ id: 7 }] })
    client.setQueryData(['saved-job-ids'], { job_ids: [42] })

    await openDialog()
    await userEvent.type(screen.getByLabelText(/type/i), 'DELETE')
    await userEvent.click(confirmButton())

    // Landed on the sign-in screen with a confirmation…
    expect(await screen.findByText(/have been deleted/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Log in' })).toBeInTheDocument()
    // …the app now treats the visitor as anonymous…
    await waitFor(() => expect(screen.getByTestId('identity')).toHaveTextContent('anonymous'))
    // …and the deleted user's data is gone from the cache, not just stale.
    expect(client.getQueryData(['profiles'])).toBeUndefined()
    expect(client.getQueryData(['saved-job-ids'])).toBeUndefined()
  })

  it('shows a server error and keeps the user signed in on failure', async () => {
    mockFetch(
      routeTable({
        'GET /api/v1/auth/me': { status: 200, json: USER },
        'DELETE /api/v1/account': {
          status: 500,
          json: {
            status: 500,
            title: 'Could not delete your account. Nothing was deleted — please try again.',
          },
        },
      }),
    )
    const { client } = renderAccount()
    await openDialog()
    await userEvent.type(screen.getByLabelText(/type/i), 'DELETE')
    await userEvent.click(confirmButton())

    expect(await screen.findByRole('alert')).toHaveTextContent(/Nothing was deleted/)
    // Still on the account page, still signed in — a failed delete must never
    // look like a logout.
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(client.getQueryData(CURRENT_USER_KEY)).toEqual(USER)
    // And it is retryable: the button is live again, not stuck pending.
    expect(confirmButton()).toBeEnabled()
  })
})
