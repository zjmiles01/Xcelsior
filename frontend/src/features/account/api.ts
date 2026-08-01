// Account deletion mutation and related cache cleanup.

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiSend } from '../../shared/api/client'
import { CURRENT_USER_KEY } from '../auth/api'

/** Permanently delete the signed-in account. The server takes the account
 * from the session cookie — there is no id to pass, and nothing the client
 * could send that would delete someone else. */
export function useDeleteAccount() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiSend<void>('DELETE', '/account'),
    onSuccess: () => {
      // Order matters. Writing the identity first notifies everything
      // observing it, so the header flips to signed-out on this tick rather
      // than after a round trip — whereas *removing* that key would leave
      // its observers holding the deleted user until their next render.
      queryClient.setQueryData(CURRENT_USER_KEY, null)
      // Then drop every other cached query outright. They hold data owned by
      // an account that no longer exists; invalidating instead would refetch
      // each one straight into a 401.
      queryClient.removeQueries({
        predicate: (query) => query.queryKey[0] !== CURRENT_USER_KEY[0],
      })
    },
  })
}
