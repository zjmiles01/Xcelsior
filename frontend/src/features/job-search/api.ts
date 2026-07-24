import { useInfiniteQuery } from '@tanstack/react-query'

import { apiGet } from '../../shared/api/client'
import type { JobListResponse } from '../../shared/api/types'
import { toSearchParams, type JobListParams } from '../../shared/filters'

export function useJobSearch(params: JobListParams) {
  return useInfiniteQuery({
    queryKey: ['jobs', params],
    queryFn: ({ pageParam }) => {
      const search = toSearchParams(params)
      if (pageParam) search.set('cursor', pageParam)
      return apiGet<JobListResponse>('/jobs', search)
    },
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  })
}
