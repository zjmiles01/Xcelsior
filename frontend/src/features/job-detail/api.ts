import { useQuery } from '@tanstack/react-query'

import { apiGet } from '../../shared/api/client'
import type { JobDetail } from '../../shared/api/types'

export type { JobDetail, JobTechnology } from '../../shared/api/types'

export function useJobDetail(jobId: number) {
  return useQuery({
    queryKey: ['job', jobId],
    queryFn: () => apiGet<JobDetail>(`/jobs/${jobId}`),
  })
}
