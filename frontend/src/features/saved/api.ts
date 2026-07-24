// Saved jobs (M10). A saved job is a persistent, per-account bookmark whose
// match info is recomputed live server-side. The search/detail UIs use the
// lightweight id set to render the Save button's state; the dashboard uses
// the full response.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiSend } from '../../shared/api/client'
import type { SavedJobIdsResponse, SavedJobsResponse } from '../../shared/api/types'

const SAVED_IDS_KEY = ['saved-job-ids'] as const
const SAVED_DASHBOARD_KEY = ['saved-jobs'] as const

/** The set of ids the current user has saved. `enabled` lets callers skip the
 * request entirely for anonymous visitors (no 401 noise). */
export function useSavedJobIds(enabled = true) {
  return useQuery({
    queryKey: SAVED_IDS_KEY,
    queryFn: () => apiGet<SavedJobIdsResponse>('/saved-jobs/ids'),
    enabled,
    staleTime: 30_000,
  })
}

export function useSavedJobs() {
  return useQuery({
    queryKey: SAVED_DASHBOARD_KEY,
    queryFn: () => apiGet<SavedJobsResponse>('/saved-jobs'),
  })
}

function useInvalidateSaved() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: SAVED_IDS_KEY })
    void queryClient.invalidateQueries({ queryKey: SAVED_DASHBOARD_KEY })
  }
}

export function useSaveJob() {
  const invalidate = useInvalidateSaved()
  return useMutation({
    mutationFn: (jobId: number) =>
      apiSend<SavedJobIdsResponse>('POST', '/saved-jobs', { job_id: jobId }),
    onSuccess: invalidate,
  })
}

export function useUnsaveJob() {
  const invalidate = useInvalidateSaved()
  return useMutation({
    mutationFn: (jobId: number) => apiSend<void>('DELETE', `/saved-jobs/${jobId}`),
    onSuccess: invalidate,
  })
}
