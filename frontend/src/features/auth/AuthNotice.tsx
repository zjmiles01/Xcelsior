import { Link } from 'react-router-dom'

import { isAuthError } from '../../shared/api/client'

/**
 * Shown inline when a request failed for auth reasons (M10). With session
 * cookies this normally means the session expired mid-use; the RequireAuth
 * guard sends fresh visits to login, but an in-flight query can still 401.
 * Offer a way back to login rather than a dead end.
 */
export function AuthNotice({ error }: { error: unknown }) {
  if (!isAuthError(error)) return null
  return (
    <p className="banner">
      Your session has expired. <Link to="/login">Log in again</Link> to continue.
    </p>
  )
}
