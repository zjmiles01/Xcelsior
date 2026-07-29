import { describe, expect, it } from 'vitest'

import { fromSearchParams, searchUrl, toSearchParams, type JobFilters } from '.'

describe('employment_type in the URL dialect', () => {
  it('serializes to the backend param name', () => {
    const params = toSearchParams({ employment_type: 'internship' })
    expect(params.get('employment_type')).toBe('internship')
  })

  it('round-trips through the URL', () => {
    const filters: JobFilters = {
      q: 'python',
      employment_type: 'internship',
      experience_level: 'entry',
    }
    expect(fromSearchParams(toSearchParams(filters))).toEqual(filters)
  })

  it('is absent when unset, so existing links are unchanged', () => {
    expect(toSearchParams({ q: 'python' }).has('employment_type')).toBe(false)
    expect(searchUrl({ q: 'python' })).toBe('/jobs?q=python')
  })

  it('survives a click-through to the skill page', () => {
    // Scope carries across surfaces: a user filtered to internships stays
    // filtered to internships when they open a skill.
    const url = searchUrl({ employment_type: 'internship', tech: ['python'] })
    expect(fromSearchParams(new URLSearchParams(url.split('?')[1]))).toEqual({
      employment_type: 'internship',
      tech: ['python'],
    })
  })
})
