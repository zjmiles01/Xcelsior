// Cross-feature queries. /meta feeds every filter UI (dashboard scope
// controls, search filter panel), so it lives here rather than in a
// feature folder.

import { useQuery } from '@tanstack/react-query'

import { apiGet } from './client'
import type { MetaResponse } from './types'

export function useMeta() {
  return useQuery({
    queryKey: ['meta'],
    queryFn: () => apiGet<MetaResponse>('/meta'),
    staleTime: 5 * 60 * 1000,
  })
}
