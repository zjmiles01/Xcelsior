import { type FormEvent, useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'

import { ApiError } from '../../shared/api/client'
import { type Credentials, useLogin, useSignup } from './api'

type Mode = 'login' | 'signup'

/** Returns the safe post-authentication redirect path. */

function safeRedirect(raw: string | null): string {
  if (!raw) return '/profile'
  const decoded = decodeURIComponent(raw)
  return decoded.startsWith('/') && !decoded.startsWith('//') ? decoded : '/profile'
}

function AuthForm({ mode }: { mode: Mode }) {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const location = useLocation()
  const target = safeRedirect(params.get('redirect'))

  // Displays a one-time confirmation after account deletion.

  const justDeleted = (location.state as { accountDeleted?: boolean } | null)?.accountDeleted

  const login = useLogin()
  const signup = useSignup()
  const action = mode === 'login' ? login : signup

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    const creds: Credentials = { email: email.trim(), password }
    action.mutate(creds, { onSuccess: () => navigate(target, { replace: true }) })
  }

  const otherMode = mode === 'login' ? 'signup' : 'login'
  const suffix = params.get('redirect') ? `?redirect=${params.get('redirect')}` : ''

  return (
    <section className="auth-page">
      <h2>{mode === 'login' ? 'Log in' : 'Create your account'}</h2>
      <p className="muted">
        {mode === 'login'
          ? 'Log in to upload a resume, run the matcher, and save jobs.'
          : 'Sign up to build your profile and track how close you are to the jobs you want.'}
      </p>

      {justDeleted && (
        <p className="banner banner--success" role="status">
          Your account and all of its data have been deleted.
        </p>
      )}

      <form onSubmit={onSubmit} className="auth-form">
        <label>
          Email
          <input
            type="email"
            autoComplete="email"
            value={email}
            required
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            value={password}
            required
            minLength={mode === 'signup' ? 8 : undefined}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {mode === 'signup' && (
          <p className="muted auth-hint">At least 8 characters.</p>
        )}

        {action.isError && (
          <p className="banner">
            {action.error instanceof ApiError ? action.error.message : 'Something went wrong.'}
          </p>
        )}

        <button className="btn btn--primary" type="submit" disabled={action.isPending}>
          {action.isPending
            ? 'Please wait…'
            : mode === 'login'
              ? 'Log in'
              : 'Sign up'}
        </button>
      </form>

      <p className="muted">
        {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
        <Link to={`/${otherMode}${suffix}`}>{mode === 'login' ? 'Sign up' : 'Log in'}</Link>
      </p>
    </section>
  )
}

export function LoginPage() {
  return <AuthForm mode="login" />
}

export function SignupPage() {
  return <AuthForm mode="signup" />
}
