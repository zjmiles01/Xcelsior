import { useQuery } from '@tanstack/react-query'

import { apiGet } from '../../shared/api/client'
import type { AnalysisResponse } from '../../shared/api/types'
import { toSearchParams, type JobFilters } from '../../shared/filters'

export type { CategoryStats, DistributionBucket, TechnologyStat } from '../../shared/api/types'
export { useMeta } from '../../shared/api/queries'

export function useAnalysis(filters: JobFilters) {
  return useQuery({
    queryKey: ['analysis', filters],
    queryFn: () => apiGet<AnalysisResponse>('/analysis', toSearchParams(filters)),
  })
}
