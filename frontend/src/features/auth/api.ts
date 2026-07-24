// Session-based auth for the SPA (M10). The server holds the session; the
// browser holds only an HTTP-only cookie it cannot read. So the client's
// notion of "who am I" comes from asking the server (`GET /auth/me`), cached
// by React Query under ['current-user']. Login/signup/logout mutate that
// cache. There is no token in localStorage — a deliberate break from M8.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, apiGet, apiSend } from '../../shared/api/client'
import type { UserOut } from '../../shared/api/types'

export type Credentials = { email: string; password: string }

export const CURRENT_USER_KEY = ['current-user'] as const

/** The signed-in user, or null when anonymous. A 401 is the normal
 * "not logged in" answer, not an error — it resolves to null. */
async function fetchCurrentUser(): Promise<UserOut | null> {
  try {
    return await apiGet<UserOut>('/auth/me')
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null
    throw error
  }
}

export function useCurrentUser() {
  return useQuery({
    queryKey: CURRENT_USER_KEY,
    queryFn: fetchCurrentUser,
    staleTime: 30_000,
    retry: false,
  })
}

/** Reset all cached data on an identity change, so one user's queries never
 * bleed into another's session. */
function useIdentityChange() {
  const queryClient = useQueryClient()
  return (user: UserOut | null) => {
    queryClient.setQueryData(CURRENT_USER_KEY, user)
    void queryClient.invalidateQueries()
  }
}

export function useSignup() {
  const onIdentityChange = useIdentityChange()
  return useMutation({
    mutationFn: (creds: Credentials) => apiSend<UserOut>('POST', '/auth/signup', creds),
    onSuccess: (user) => onIdentityChange(user),
  })
}

export function useLogin() {
  const onIdentityChange = useIdentityChange()
  return useMutation({
    mutationFn: (creds: Credentials) => apiSend<UserOut>('POST', '/auth/login', creds),
    onSuccess: (user) => onIdentityChange(user),
  })
}

export function useLogout() {
  const onIdentityChange = useIdentityChange()
  return useMutation({
    mutationFn: () => apiSend<void>('POST', '/auth/logout'),
    onSuccess: () => onIdentityChange(null),
  })
}
