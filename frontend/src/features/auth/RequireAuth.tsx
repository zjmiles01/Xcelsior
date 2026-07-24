import { type ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { useCurrentUser } from './api'

/**
 * Gate for the authenticated surface (M10). Visitors browse jobs, market
 * intelligence, and job details freely; the personal actions (profile,
 * matcher, saved jobs) live behind this. An anonymous visitor is sent to
 * /login with a `redirect` back to where they were headed, so they land on
 * the action they wanted after signing in.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { data: user, isPending } = useCurrentUser()
  const location = useLocation()

  if (isPending) return <p className="muted">Checking your session…</p>
  if (!user) {
    const redirect = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?redirect=${redirect}`} replace />
  }
  return <>{children}</>
}
