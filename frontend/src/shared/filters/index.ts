// The single home of the URL filter dialect. Every surface (dashboard,
// job search, skill pages) serializes and parses search state through this
// module, so links between surfaces always agree — and a dashboard stat's
// click-through URL is just "current filters plus one more".
//
// Param names mirror the backend contract (app/catalog/deps.py) exactly:
// the URL the user sees is the API query the server answers.

import type { ApiJobFilters } from '../api/types'

export interface JobFilters {
  q?: string
  title?: string
  location?: string
  radius_miles?: number
  tech?: string[]
  arrangement?: 'onsite' | 'hybrid' | 'remote'
  experience_level?: 'entry' | 'mid' | 'senior' | 'staff_plus'
  salary_min?: number
}

export type SortOption = 'recency' | 'salary' | 'relevance'

export interface JobListParams extends JobFilters {
  sort?: SortOption
  limit?: number
}

export const RADIUS_OPTIONS = [10, 25, 50, 100]

export function toSearchParams(params: JobListParams): URLSearchParams {
  const searchParams = new URLSearchParams()
  if (params.q) searchParams.set('q', params.q)
  if (params.title) searchParams.set('title', params.title)
  if (params.location) {
    searchParams.set('location', params.location)
    if (params.radius_miles !== undefined) {
      searchParams.set('radius_miles', String(params.radius_miles))
    }
  }
  for (const slug of params.tech ?? []) {
    searchParams.append('tech', slug)
  }
  if (params.arrangement) searchParams.set('arrangement', params.arrangement)
  if (params.experience_level) searchParams.set('experience_level', params.experience_level)
  if (params.salary_min !== undefined) searchParams.set('salary_min', String(params.salary_min))
  if (params.sort) searchParams.set('sort', params.sort)
  if (params.limit !== undefined) searchParams.set('limit', String(params.limit))
  return searchParams
}

export function fromSearchParams(searchParams: URLSearchParams): JobFilters {
  const filters: JobFilters = {}
  const q = searchParams.get('q')
  if (q) filters.q = q
  const title = searchParams.get('title')
  if (title) filters.title = title
  const location = searchParams.get('location')
  if (location) {
    filters.location = location
    const radius = Number(searchParams.get('radius_miles'))
    if (radius) filters.radius_miles = radius
  }
  const tech = searchParams.getAll('tech')
  if (tech.length > 0) filters.tech = tech
  const arrangement = searchParams.get('arrangement')
  if (arrangement) filters.arrangement = arrangement as JobFilters['arrangement']
  const level = searchParams.get('experience_level')
  if (level) filters.experience_level = level as JobFilters['experience_level']
  const salaryMin = Number(searchParams.get('salary_min'))
  if (salaryMin) filters.salary_min = salaryMin
  return filters
}

/** Server-shaped filters (e.g. a relaxation option) back into the URL dialect. */
export function fromApiFilters(api: ApiJobFilters): JobFilters {
  const filters: JobFilters = {}
  if (api.q) filters.q = api.q
  if (api.title) filters.title = api.title
  if (api.location) {
    filters.location = api.location
    filters.radius_miles = api.radius_miles
  }
  if (api.technologies && api.technologies.length > 0) filters.tech = api.technologies
  if (api.arrangement) filters.arrangement = api.arrangement
  if (api.experience_level) filters.experience_level = api.experience_level
  if (api.salary_min != null) filters.salary_min = api.salary_min
  return filters
}

/** The click-through builder: current scope plus one more constraint. */
export function withTech(filters: JobFilters, slug: string): JobFilters {
  const tech = filters.tech ?? []
  return tech.includes(slug) ? filters : { ...filters, tech: [...tech, slug] }
}

export function searchUrl(filters: JobListParams): string {
  const params = toSearchParams(filters)
  const query = params.toString()
  return query ? `/jobs?${query}` : '/jobs'
}

/** Skill page for a technology, carrying the current scope along. The
 * skill itself is the page's subject, not a filter, so it's removed. */
export function skillUrl(slug: string, filters: JobFilters = {}): string {
  const scope = { ...filters, tech: filters.tech?.filter((t) => t !== slug) }
  if (scope.tech?.length === 0) delete scope.tech
  const params = toSearchParams(scope)
  const query = params.toString()
  return query ? `/skills/${slug}?${query}` : `/skills/${slug}`
}
