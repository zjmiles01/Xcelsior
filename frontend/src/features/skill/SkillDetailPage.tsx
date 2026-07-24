import { useEffect } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { useMeta } from '../../shared/api/queries'
import type { DistributionBucket, SkillDetailResponse } from '../../shared/api/types'
import {
  fromSearchParams,
  searchUrl,
  skillUrl,
  toSearchParams,
  withTech,
  type JobFilters,
} from '../../shared/filters'
import { useSkillDetail } from './api'

const LEVEL_LABELS: Record<string, string> = {
  entry: 'Entry',
  mid: 'Mid',
  senior: 'Senior',
  staff_plus: 'Staff+',
  unspecified: 'Unspecified',
}

const REQUIREMENT_LABELS: Record<string, string> = {
  required: 'Required',
  preferred: 'Nice to have',
  mentioned: 'Mentioned',
}

export function SkillDetailPage() {
  const { slug = '' } = useParams()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = fromSearchParams(searchParams)
  const { data, isPending, isError } = useSkillDetail(slug, filters)
  const { data: meta } = useMeta()

  // Alias slugs redirect at the API; mirror the canonical slug into the
  // address bar so shared links never fork a skill's identity.
  useEffect(() => {
    if (data && data.header.slug !== slug) {
      navigate(skillUrl(data.header.slug, filters), { replace: true })
    }
  })

  if (isPending) return <p>Loading skill…</p>
  if (isError || !data) return <p>Unknown skill.</p>

  const { header, salary } = data
  const pct = (share: number) => `${Math.round(share * 100)}%`

  return (
    <article>
      <ScopePills filters={filters} meta={meta} onChange={(f) => setSearchParams(toSearchParams(f))} />
      <header className="dashboard-header">
        <div>
          <h2>
            {header.name} <small className="muted">{header.category.replace('_', '/')}</small>
          </h2>
          <p className="muted">
            <Link to={searchUrl(withTech(filters, header.slug))}>
              {header.jobs_with_tech.toLocaleString()} jobs
            </Link>{' '}
            of {header.analyzed_jobs.toLocaleString()} in scope ({pct(header.share)}) —{' '}
            <Link to={searchUrl(withTech(filters, header.slug))}>view all →</Link>
          </p>
        </div>
        {salary.median !== null && <SalarySummary data={data} />}
      </header>

      {header.low_confidence && (
        <p className="banner">
          Only {header.jobs_with_tech} jobs in this scope mention {header.name} — below our{' '}
          {header.min_sample_size}-job threshold, so treat these numbers as anecdotes, not
          statistics.
        </p>
      )}

      <div className="dashboard-panels">
        <DistPanel
          title="How it's asked for"
          buckets={data.requirement_levels}
          labels={REQUIREMENT_LABELS}
        />
        <DistPanel title="Work arrangement" buckets={data.arrangements} />
        <DistPanel title="Experience level" buckets={data.experience_levels} labels={LEVEL_LABELS} />
      </div>

      <div className="dashboard-panels">
        <CoOccurring data={data} filters={filters} />
        <TrendPanel data={data} />
      </div>
    </article>
  )
}

function ScopePills({
  filters,
  meta,
  onChange,
}: {
  filters: JobFilters
  meta: ReturnType<typeof useMeta>['data']
  onChange: (next: JobFilters) => void
}) {
  const location = meta?.locations.find((l) => l.slug === filters.location)
  const title = meta?.titles.find((t) => t.slug === filters.title)
  return (
    <div className="scope-controls">
      <span className="hint">Scope:</span>
      {filters.location ? (
        <>
          <button
            className="tech-pill"
            title="Remove location scope"
            onClick={() => onChange({ ...filters, location: undefined, radius_miles: undefined })}
          >
            {location?.label ?? filters.location} · {filters.radius_miles ?? 50}mi ✕
          </button>
          <button
            className="clear-scope"
            onClick={() => onChange({ ...filters, location: undefined, radius_miles: undefined })}
          >
            Switch to national
          </button>
        </>
      ) : (
        <span className="fact">National</span>
      )}
      {filters.title && (
        <button
          className="tech-pill"
          title="Remove role scope"
          onClick={() => onChange({ ...filters, title: undefined })}
        >
          {title?.name ?? filters.title} ✕
        </button>
      )}
      {filters.tech?.map((slug) => (
        <button
          key={slug}
          className="tech-pill"
          title="Remove from scope"
          onClick={() => onChange({ ...filters, tech: filters.tech?.filter((t) => t !== slug) })}
        >
          {slug} ✕
        </button>
      ))}
    </div>
  )
}

function SalarySummary({ data }: { data: SkillDetailResponse }) {
  const { salary } = data
  const fmt = (n: number) => `$${Math.round(n / 1000)}k`
  const delta = salary.delta_vs_national
  return (
    <div className="salary-summary">
      <strong>{fmt(salary.median!)}</strong> median{' '}
      {delta !== null && delta !== 0 && (
        <span className={delta > 0 ? 'delta-up' : 'delta-down'}>
          {delta > 0 ? '+' : '−'}
          {fmt(Math.abs(delta))} vs national
        </span>
      )}
      {delta === 0 && <span className="muted">matches national median</span>}
      <br />
      <span className="muted">
        {fmt(salary.p25!)}–{fmt(salary.p75!)} middle half · {salary.disclosed_count.toLocaleString()}{' '}
        disclosed
      </span>
    </div>
  )
}

function DistPanel({
  title,
  buckets,
  labels,
}: {
  title: string
  buckets: DistributionBucket[]
  labels?: Record<string, string>
}) {
  if (buckets.length === 0) return null
  return (
    <div className="panel">
      <h4>{title}</h4>
      {buckets.map((bucket) => (
        <div key={bucket.value} className="dist-row">
          <span className="dist-label">{labels?.[bucket.value] ?? bucket.value}</span>
          <div className="dist-bar">
            <div className="dist-fill" style={{ width: `${bucket.share * 100}%` }} />
          </div>
          <span className="dist-count">
            {bucket.count.toLocaleString()} ({Math.round(bucket.share * 100)}%)
          </span>
        </div>
      ))}
    </div>
  )
}

/**
 * Pairings that beat the base rate by the server's lift floor. The lift
 * is shown, not hidden — "appears together" without "more than chance"
 * would be the spurious-pairing trap the floor exists to avoid.
 */
function CoOccurring({ data, filters }: { data: SkillDetailResponse; filters: JobFilters }) {
  if (data.co_occurring.length === 0) {
    return (
      <div className="panel">
        <h4>Often paired with</h4>
        <p className="muted">No technology clears the pairing bar in this scope.</p>
      </div>
    )
  }
  return (
    <div className="panel">
      <h4>Often paired with</h4>
      <ul className="tech-rows">
        {data.co_occurring.map((pair) => (
          <li key={pair.slug}>
            <Link className="tech-row" to={skillUrl(pair.slug, filters)}>
              <span className="tech-name">{pair.name}</span>
              <span className="tech-bar">
                <span
                  className="tech-fill"
                  style={{ width: `${pair.share_given_tech * 100}%` }}
                />
              </span>
              <span
                className="tech-count"
                title={`${pair.count} of ${data.header.jobs_with_tech} ${data.header.name} jobs; ${(pair.lift).toFixed(1)}× its base rate in this scope`}
              >
                {Math.round(pair.share_given_tech * 100)}%
                <small> ({pair.lift.toFixed(1)}×)</small>
              </span>
            </Link>
          </li>
        ))}
      </ul>
      <p className="hint">
        % of {data.header.name} jobs that also mention it · ×lift over its scope base rate
      </p>
    </div>
  )
}

function TrendPanel({ data }: { data: SkillDetailResponse }) {
  const { trend } = data
  if (trend.status === 'collecting_history') {
    return (
      <div className="panel">
        <h4>Demand trend</h4>
        <p className="muted">
          Collecting history: {trend.days_observed} of {trend.min_days} snapshot days observed.
          A trend line appears once enough days accumulate to mean something.
        </p>
      </div>
    )
  }
  const max = Math.max(...trend.points.map((p) => p.job_count), 1)
  const width = 260
  const height = 60
  const step = trend.points.length > 1 ? width / (trend.points.length - 1) : 0
  const line = trend.points
    .map((p, i) => `${(i * step).toFixed(1)},${(height - (p.job_count / max) * height).toFixed(1)}`)
    .join(' ')
  const first = trend.points[0]
  const last = trend.points[trend.points.length - 1]
  return (
    <div className="panel">
      <h4>
        Demand trend <small className="muted">({trend.geo_slug === 'national' ? 'national' : trend.geo_slug})</small>
      </h4>
      <svg
        viewBox={`0 0 ${width} ${height + 4}`}
        className="trend-chart"
        role="img"
        aria-label={`Job count from ${first.snapshot_date} (${first.job_count}) to ${last.snapshot_date} (${last.job_count})`}
      >
        <polyline points={line} fill="none" stroke="#7c9be8" strokeWidth="2" />
      </svg>
      <p className="hint">
        {first.snapshot_date}: {first.job_count.toLocaleString()} → {last.snapshot_date}:{' '}
        {last.job_count.toLocaleString()} jobs
      </p>
    </div>
  )
}
