import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiSend } from '../../shared/api/client'
import type {
  ProfileDetail,
  ProfileListResponse,
  ProfileMatchesResponse,
  ProfileUpdate,
} from '../../shared/api/types'
import { toSearchParams, type JobFilters } from '../../shared/filters'

export type {
  ProfileDetail,
  ProfileEducation,
  ProfileExperience,
  ProfileListItem,
  ProfileSkill,
  ProfileUpdate,
} from '../../shared/api/types'

export function useProfiles() {
  return useQuery({
    queryKey: ['profiles'],
    queryFn: () => apiGet<ProfileListResponse>('/profiles'),
  })
}

export function useProfile(id: number) {
  return useQuery({
    queryKey: ['profile', id],
    queryFn: () => apiGet<ProfileDetail>(`/profiles/${id}`),
  })
}

/**
 * Ranked job matches for a reviewed profile (M9). The scope is the same
 * URL filter dialect the market surface uses, serialized through the shared
 * builder so the candidate pool is drawn the exact way search/analytics
 * draw theirs. Server-ranked by score; no client sort. The endpoint 409s on
 * an unreviewed profile, so the caller must handle that state.
 */
export function useProfileMatches(id: number, filters: JobFilters, limit = 50) {
  const params = toSearchParams({ ...filters, limit })
  return useQuery({
    queryKey: ['profile-matches', id, params.toString()],
    queryFn: () => apiGet<ProfileMatchesResponse>(`/profiles/${id}/matches`, params),
  })
}

export function useUploadResume() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return apiSend<ProfileDetail>('POST', '/resumes', form)
    },
    onSuccess: (profile) => {
      queryClient.setQueryData(['profile', profile.id], profile)
      void queryClient.invalidateQueries({ queryKey: ['profiles'] })
    },
  })
}

export function useUpdateProfile(id: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: ProfileUpdate) =>
      apiSend<ProfileDetail>('PUT', `/profiles/${id}`, payload),
    onSuccess: (profile) => {
      queryClient.setQueryData(['profile', id], profile)
      void queryClient.invalidateQueries({ queryKey: ['profiles'] })
    },
  })
}

export function useReextractProfile(id: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiSend<ProfileDetail>('POST', `/profiles/${id}/reextract`),
    onSuccess: (profile) => {
      queryClient.setQueryData(['profile', id], profile)
      void queryClient.invalidateQueries({ queryKey: ['profiles'] })
    },
  })
}

export function useDeleteProfile(id: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiSend<void>('DELETE', `/profiles/${id}`),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: ['profile', id] })
      void queryClient.invalidateQueries({ queryKey: ['profiles'] })
    },
  })
}
