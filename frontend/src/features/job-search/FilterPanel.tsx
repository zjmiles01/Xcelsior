import type { FormEvent } from 'react'

import type { MetaResponse } from '../../shared/api/types'
import { MapPin, Search } from '../home/icons'
import { RADIUS_OPTIONS, type JobFilters } from '../../shared/filters'

const ARRANGEMENTS = ['onsite', 'hybrid', 'remote'] as const
const LEVELS = [
  ['entry', 'Entry'],
  ['mid', 'Mid'],
  ['senior', 'Senior'],
  ['staff_plus', 'Staff+'],
] as const

const LEVEL_LABELS: Record<string, string> = {
  entry: 'Entry',
  mid: 'Mid',
  senior: 'Senior',
  staff_plus: 'Staff+',
}

// 'unknown' is deliberately not offered: it is a classifier outcome, not
// something a job seeker searches for. The API still accepts it.
const EMPLOYMENT_TYPES = [
  ['full_time', 'Full-time'],
  ['part_time', 'Part-time'],
  ['internship', 'Internship'],
  ['contract', 'Contract'],
  ['temporary', 'Temporary'],
] as const

const EMPLOYMENT_TYPE_LABELS: Record<string, string> = {
  full_time: 'Full-time',
  part_time: 'Part-time',
  internship: 'Internship',
  contract: 'Contract',
  temporary: 'Temporary',
  unknown: 'Unspecified type',
}

const CATEGORY_LABELS: Record<string, string> = {
  languages: 'Languages',
  frameworks: 'Frameworks',
  cloud: 'Cloud',
  infrastructure: 'Infrastructure & DevOps',
  databases: 'Databases',
  testing: 'Testing',
  messaging: 'Messaging & Streaming',
  data_engineering: 'Data Engineering',
  ai_ml: 'AI / ML',
  security: 'Security',
}

const SALARY_STEPS = [100_000, 150_000, 200_000, 250_000, 300_000]

/**
 * Search + filter controls (jobs). Every control writes straight into the URL
 * (via onChange -> setSearchParams), so any search is a shareable link and the
 * back button walks filter history. Restyled into a search bar, a pill row,
 * and a removable active-filter chip row — the underlying filter dialect and
 * behavior are unchanged.
 */
export function FilterPanel({
  filters,
  meta,
  onChange,
}: {
  filters: JobFilters
  meta: MetaResponse | undefined
  onChange: (next: JobFilters) => void
}) {
  const techBySlug = new Map(meta?.technologies.map((t) => [t.slug, t]) ?? [])
  const titleBySlug = new Map(meta?.titles.map((t) => [t.slug, t]) ?? [])

  function submitQuery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const value = new FormData(event.currentTarget).get('q')?.toString().trim()
    onChange({ ...filters, q: value || undefined })
  }

  // Active filters as removable chips (matches the mockup's chip row).
  const chips: { key: string; label: string; onRemove: () => void }[] = []
  if (filters.title) {
    chips.push({
      key: `title:${filters.title}`,
      label: titleBySlug.get(filters.title)?.name ?? filters.title,
      onRemove: () => onChange({ ...filters, title: undefined }),
    })
  }
  if (filters.arrangement) {
    chips.push({
      key: `arr:${filters.arrangement}`,
      label: cap(filters.arrangement),
      onRemove: () => onChange({ ...filters, arrangement: undefined }),
    })
  }
  if (filters.experience_level) {
    chips.push({
      key: `exp:${filters.experience_level}`,
      label: LEVEL_LABELS[filters.experience_level] ?? filters.experience_level,
      onRemove: () => onChange({ ...filters, experience_level: undefined }),
    })
  }
  if (filters.employment_type) {
    chips.push({
      key: `emp:${filters.employment_type}`,
      label: EMPLOYMENT_TYPE_LABELS[filters.employment_type] ?? filters.employment_type,
      onRemove: () => onChange({ ...filters, employment_type: undefined }),
    })
  }
  if (filters.salary_min !== undefined) {
    chips.push({
      key: 'salary',
      label: `$${filters.salary_min / 1000}k+`,
      onRemove: () => onChange({ ...filters, salary_min: undefined }),
    })
  }
  for (const slug of filters.tech ?? []) {
    chips.push({
      key: `tech:${slug}`,
      label: techBySlug.get(slug)?.name ?? slug,
      onRemove: () => onChange({ ...filters, tech: filters.tech?.filter((t) => t !== slug) }),
    })
  }

  return (
    <div className="jobs-filters">
      <form className="searchbar" onSubmit={submitQuery}>
        <div className="searchbar__field">
          <Search className="searchbar__icon" size={18} />
          <input
            type="search"
            name="q"
            defaultValue={filters.q ?? ''}
            key={filters.q ?? ''}
            aria-label="Job title, keyword, or skill"
            placeholder="Job title, keyword, or skill"
          />
        </div>

        <div className="searchbar__divider" />

        <div className="searchbar__field">
          <MapPin className="searchbar__icon" size={18} />
          <select
            aria-label="Location"
            value={filters.location ?? ''}
            onChange={(e) =>
              onChange({
                ...filters,
                location: e.target.value || undefined,
                radius_miles: e.target.value ? (filters.radius_miles ?? 50) : undefined,
              })
            }
          >
            <option value="">Nationwide</option>
            {meta?.locations.map((l) => (
              <option key={l.slug} value={l.slug}>
                {l.label}
              </option>
            ))}
          </select>
        </div>

        {filters.location && (
          <select
            className="searchbar__radius"
            aria-label="Radius"
            value={filters.radius_miles ?? 50}
            onChange={(e) => onChange({ ...filters, radius_miles: Number(e.target.value) })}
          >
            {RADIUS_OPTIONS.map((r) => (
              <option key={r} value={r}>
                {r} miles
              </option>
            ))}
          </select>
        )}

        <button type="submit" className="btn btn--primary searchbar__submit">
          <Search size={17} />
          Search Jobs
        </button>
      </form>

      <div className="filter-pills">
        <select
          className="filter-pill"
          aria-label="Role"
          value={filters.title ?? ''}
          onChange={(e) => onChange({ ...filters, title: e.target.value || undefined })}
        >
          <option value="">Role</option>
          {meta?.titles.map((t) => (
            <option key={t.slug} value={t.slug}>
              {t.name}
            </option>
          ))}
        </select>

        <select
          className="filter-pill"
          aria-label="Experience"
          value={filters.experience_level ?? ''}
          onChange={(e) =>
            onChange({
              ...filters,
              experience_level: (e.target.value || undefined) as JobFilters['experience_level'],
            })
          }
        >
          <option value="">Experience</option>
          {LEVELS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>

        <select
          className="filter-pill"
          aria-label="Work style"
          value={filters.arrangement ?? ''}
          onChange={(e) =>
            onChange({
              ...filters,
              arrangement: (e.target.value || undefined) as JobFilters['arrangement'],
            })
          }
        >
          <option value="">Work style</option>
          {ARRANGEMENTS.map((a) => (
            <option key={a} value={a}>
              {cap(a)}
            </option>
          ))}
        </select>

        <select
          className="filter-pill"
          aria-label="Employment type"
          value={filters.employment_type ?? ''}
          onChange={(e) =>
            onChange({
              ...filters,
              employment_type: (e.target.value || undefined) as JobFilters['employment_type'],
            })
          }
        >
          <option value="">Employment type</option>
          {EMPLOYMENT_TYPES.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>

        <select
          className="filter-pill"
          aria-label="Salary"
          value={filters.salary_min ?? ''}
          onChange={(e) =>
            onChange({
              ...filters,
              salary_min: e.target.value ? Number(e.target.value) : undefined,
            })
          }
        >
          <option value="">Salary</option>
          {SALARY_STEPS.map((v) => (
            <option key={v} value={v}>
              ${v / 1000}k+
            </option>
          ))}
        </select>

        <select
          className="filter-pill"
          aria-label="Technology"
          value=""
          onChange={(e) => {
            if (!e.target.value) return
            const tech = filters.tech ?? []
            if (!tech.includes(e.target.value)) {
              onChange({ ...filters, tech: [...tech, e.target.value] })
            }
          }}
        >
          <option value="">Technology</option>
          {Object.entries(CATEGORY_LABELS).map(([category, label]) => {
            const options = meta?.technologies.filter((t) => t.category === category) ?? []
            if (options.length === 0) return null
            return (
              <optgroup key={category} label={label}>
                {options.map((t) => (
                  <option key={t.slug} value={t.slug}>
                    {t.name}
                  </option>
                ))}
              </optgroup>
            )
          })}
        </select>
      </div>

      {chips.length > 0 && (
        <div className="active-chips">
          {chips.map((chip) => (
            <button
              key={chip.key}
              type="button"
              className="tech-pill"
              title="Remove filter"
              onClick={chip.onRemove}
            >
              {chip.label} ✕
            </button>
          ))}
          <button type="button" className="clear-scope" onClick={() => onChange({})}>
            Clear all
          </button>
        </div>
      )}

      {filters.salary_min !== undefined && (
        <p className="hint">
          The salary filter only matches jobs that disclose pay — postings without a stated
          salary are excluded, not assumed to qualify.
        </p>
      )}
    </div>
  )
}

function cap(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}
