import { useQuery } from '@tanstack/react-query'

import { apiGet } from '../../shared/api/client'
import type { SkillDetailResponse } from '../../shared/api/types'
import { toSearchParams, type JobFilters } from '../../shared/filters'

export type { CoOccurrenceStat, SkillDetailResponse } from '../../shared/api/types'

// Alias slugs 301 server-side; fetch follows the redirect, so the
// response's header.slug is always canonical — the page uses that to
// rewrite the URL in place.
export function useSkillDetail(slug: string, filters: JobFilters) {
  return useQuery({
    queryKey: ['skill', slug, filters],
    queryFn: () => apiGet<SkillDetailResponse>(`/skills/${slug}`, toSearchParams(filters)),
  })
}
