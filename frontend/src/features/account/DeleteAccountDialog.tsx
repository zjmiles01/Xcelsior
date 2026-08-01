import { type FormEvent, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { ApiError } from '../../shared/api/client'
import { useDeleteAccount } from './api'

/** Required confirmation text for account deletion. */
export const CONFIRM_PHRASE = 'DELETE'

/** Confirmation modal for permanent account deletion. */

export function DeleteAccountDialog({ email, onClose }: { email: string; onClose: () => void }) {
  const navigate = useNavigate()
  const remove = useDeleteAccount()
  const [typed, setTyped] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const pending = remove.isPending
  const confirmed = typed.trim() === CONFIRM_PHRASE

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // Escape closes the dialog — but never mid-request: the delete is already
  // on its way to the server and the UI must not pretend otherwise.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !pending) onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose, pending])

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    // The button is disabled in both cases; this guards the paths that skip
    // it (Enter on a held key, a double submit landing before the re-render).
    if (!confirmed || pending) return
    remove.mutate(undefined, {
      onSuccess: () => navigate('/login', { replace: true, state: { accountDeleted: true } }),
    })
  }

  return (
    <div
      className="modal-backdrop"
      onClick={() => {
        if (!pending) onClose()
      }}
    >
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-account-title"
        onClick={(event) => event.stopPropagation()}
      >
        <h3 id="delete-account-title" className="modal__title">
          Delete your account?
        </h3>
        <p className="modal__body">
          This permanently deletes <strong>{email}</strong> and everything it owns: your
          uploaded resumes, your candidate profiles and every skill and role extracted from
          them, and your saved jobs. This cannot be undone, and support cannot restore it.
        </p>

        <form onSubmit={onSubmit} className="modal__form">
          <label htmlFor="delete-account-confirm">
            Type <code>{CONFIRM_PHRASE}</code> to confirm
          </label>
          <input
            id="delete-account-confirm"
            ref={inputRef}
            type="text"
            value={typed}
            autoComplete="off"
            disabled={pending}
            onChange={(event) => setTyped(event.target.value)}
          />

          {remove.isError && (
            <p className="banner" role="alert">
              {remove.error instanceof ApiError
                ? remove.error.message
                : 'Something went wrong. Your account was not deleted.'}
            </p>
          )}

          <div className="modal__actions">
            <button type="button" className="btn" onClick={onClose} disabled={pending}>
              Cancel
            </button>
            <button type="submit" className="btn btn--danger" disabled={!confirmed || pending}>
              {pending ? 'Deleting…' : 'Delete my account'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
