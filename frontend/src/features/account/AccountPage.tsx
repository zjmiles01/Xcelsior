import { useState } from 'react'

import { useCurrentUser } from '../auth/api'
import { DeleteAccountDialog } from './DeleteAccountDialog'

/**
 * /account — account settings for the signed-in user (M11). Thin today:
 * the address the account is keyed on, and the one irreversible action in
 * the product, fenced off in its own danger zone so it can never be
 * mistaken for the ordinary controls above it.
 *
 * Rendered behind RequireAuth, so `user` is present by the time this paints.
 */
export function AccountPage() {
  const { data: user } = useCurrentUser()
  const [confirming, setConfirming] = useState(false)

  if (!user) return null

  return (
    <section className="account-page">
      <h2>Account</h2>
      <p className="muted">
        You are signed in as <strong>{user.email}</strong>.
      </p>

      <div className="danger-zone">
        <h3 className="danger-zone__title">Danger zone</h3>
        <p className="danger-zone__body">
          Deleting your account permanently removes your resumes, candidate profiles, the
          skills and experience extracted from them, and your saved jobs. Your account cannot
          be recovered afterwards, and neither can the data.
        </p>
        <button
          type="button"
          className="btn btn--danger"
          onClick={() => setConfirming(true)}
        >
          Delete account
        </button>
      </div>

      {confirming && (
        <DeleteAccountDialog email={user.email} onClose={() => setConfirming(false)} />
      )}
    </section>
  )
}
