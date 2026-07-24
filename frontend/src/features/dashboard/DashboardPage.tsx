import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { relativeTimeSince } from '../../shared/format/time'
import { BarChart, Briefcase, ClipboardList, DollarSign, MapPin } from '../home/icons'
import {
  fromSearchParams,
  searchUrl,
  toSearchParams,
  RADIUS_OPTIONS,
  type JobFilters,
} from '../../shared/filters'
import { useAnalysis, useMeta, type DistributionBucket } from './api'
import { CategoryCard } from './CategoryCard'

type AnalysisData = NonNullable<ReturnType<typeof useAnalysis>['data']>

const LEVEL_LABELS: Record<string, string> = {
  entry: 'Entry',
  mid: 'Mid',
  senior: 'Senior',
  staff_plus: 'Staff+',
  unspecified: 'Unspecified',
}

type Tab = 'overview' | 'experience' | 'companies' | 'salary'

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Skills Overview' },
  { id: 'experience', label: 'Experience & Arrangement' },
  { id: 'companies', label: 'Top Companies' },
  { id: 'salary', label: 'Salary Insights' },
]

const fmtK = (n: number) => `$${Math.round(n / 1000)}K`

export function DashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = fromSearchParams(searchParams)
  const { data, isPending, isError } = useAnalysis(filters)
  const { data: meta } = useMeta()
  const [tab, setTab] = useState<Tab>('overview')

  function update(next: JobFilters) {
    setSearchParams(toSearchParams(next), { replace: false })
  }

  return (
    <section className="skills">
      <header className="skl-intro">
        <span className="eyebrow eyebrow--pill">Skills intelligence</span>
        <h1 className="skl-title">
          See the skills, technologies, and experience levels employers value most.
        </h1>
        <p className="skl-lead">
          Choose a role and location to analyze real job market data and discover what you
          should learn next.
        </p>
      </header>

      <FilterCard filters={filters} meta={meta} onChange={update} />

      {isError ? (
        <p className="banner skl-status">
          Could not load the market analysis. Is the backend running?
        </p>
      ) : isPending || !data ? (
        <SkillsSkeleton />
      ) : (
        <>
          {data.header.low_confidence && (
            <p className="banner">
              Only {data.header.analyzed_jobs} jobs match this scope — below our{' '}
              {data.header.min_sample_size}-job threshold, so treat these numbers as anecdotes,
              not statistics. Try widening the radius or removing a filter.
            </p>
          )}

          <StatTiles data={data} filters={filters} />

          <div className="skl-tabs" role="tablist" aria-label="Market analysis views">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                className={`skl-tab${tab === t.id ? ' skl-tab--active' : ''}`}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="skl-panel" role="tabpanel">
            {tab === 'overview' && <Overview data={data} filters={filters} />}
            {tab === 'experience' && <ExperienceArrangement data={data} filters={filters} />}
            {tab === 'companies' && <TopCompanies data={data} />}
            {tab === 'salary' && <SalaryInsights data={data} />}
          </div>
        </>
      )}
    </section>
  )
}

/* ── Filter card ──────────────────────────────────────────────────────── */

function FilterCard({
  filters,
  meta,
  onChange,
}: {
  filters: JobFilters
  meta: ReturnType<typeof useMeta>['data']
  onChange: (next: JobFilters) => void
}) {
  const hasScope =
    filters.title ||
    filters.location ||
    filters.tech?.length ||
    filters.arrangement ||
    filters.experience_level ||
    filters.salary_min

  // Selects apply live (below); the button is an explicit "apply" affordance
  // that matches the mockup without changing the live-filtering behavior.
  return (
    <form className="filter-card" onSubmit={(e) => e.preventDefault()}>
      <div className="filter-card__fields">
        <label className="field">
          <span className="field__label">Role</span>
          <span className="field__control">
            <Briefcase className="field__icon" size={16} />
            <select
              value={filters.title ?? ''}
              onChange={(e) => onChange({ ...filters, title: e.target.value || undefined })}
            >
              <option value="">All roles</option>
              {meta?.titles.map((t) => (
                <option key={t.slug} value={t.slug}>
                  {t.name}
                </option>
              ))}
            </select>
          </span>
        </label>

        <label className="field">
          <span className="field__label">Location</span>
          <span className="field__control">
            <MapPin className="field__icon" size={16} />
            <select
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
          </span>
        </label>

        {filters.location && (
          <label className="field field--radius">
            <span className="field__label">Radius</span>
            <span className="field__control">
              <select
                value={filters.radius_miles ?? 50}
                onChange={(e) => onChange({ ...filters, radius_miles: Number(e.target.value) })}
              >
                {RADIUS_OPTIONS.map((r) => (
                  <option key={r} value={r}>
                    {r} miles
                  </option>
                ))}
              </select>
            </span>
          </label>
        )}

        <button type="submit" className="btn btn--primary filter-card__submit">
          Analyze Market
        </button>
      </div>

      {hasScope ? (
        <div className="filter-card__scope">
          {filters.tech?.map((slug) => (
            <button
              key={slug}
              type="button"
              className="tech-pill"
              title="Remove from scope"
              onClick={() =>
                onChange({ ...filters, tech: filters.tech?.filter((t) => t !== slug) })
              }
            >
              {slug} ✕
            </button>
          ))}
          <button type="button" className="clear-scope" onClick={() => onChange({})}>
            Clear
          </button>
        </div>
      ) : null}
    </form>
  )
}

/* ── Stat tiles ───────────────────────────────────────────────────────── */

function StatTiles({ data, filters }: { data: AnalysisData; filters: JobFilters }) {
  const { header, salary } = data
  const salaryPct = Math.round((header.salary_disclosed / header.analyzed_jobs) * 100)

  return (
    <div className="stat-tiles">
      <Link className="stat-tile" to={searchUrl(filters)}>
        <span className="icon-circle">
          <ClipboardList size={22} />
        </span>
        <span className="stat-tile__body">
          <strong className="stat-tile__value">{header.analyzed_jobs.toLocaleString()}</strong>
          <span className="stat-tile__label">Jobs analyzed</span>
          <span className="stat-tile__sub">Updated {relativeTimeSince(data.computed_at)}</span>
        </span>
      </Link>

      <div className="stat-tile">
        <span className="icon-circle">
          <BarChart size={22} />
        </span>
        <span className="stat-tile__body">
          <strong className="stat-tile__value">
            {header.salary_disclosed.toLocaleString()}
          </strong>
          <span className="stat-tile__label">Jobs with salary data</span>
          <span className="stat-tile__sub">{salaryPct}% of total jobs</span>
        </span>
      </div>

      <div className="stat-tile">
        <span className="icon-circle">
          <DollarSign size={22} />
        </span>
        <span className="stat-tile__body">
          <strong className="stat-tile__value">
            {salary.median !== null ? fmtK(salary.median) : '—'}
          </strong>
          <span className="stat-tile__label">Median disclosed salary</span>
          <span className="stat-tile__sub">
            {salary.median !== null && salary.p25 !== null && salary.p75 !== null
              ? `${fmtK(salary.p25)} – ${fmtK(salary.p75)} middle 50%`
              : 'Not enough disclosed salaries'}
          </span>
        </span>
      </div>
    </div>
  )
}

/* ── Tab panels ───────────────────────────────────────────────────────── */

function Overview({ data, filters }: { data: AnalysisData; filters: JobFilters }) {
  const categories = data.categories.filter((c) => c.technologies.length > 0)
  if (categories.length === 0) {
    return <p className="muted skl-empty">No skill data for this scope yet.</p>
  }
  return (
    <div className="cat-grid">
      {categories.map((category) => (
        <CategoryCard
          key={category.category}
          category={category}
          filters={filters}
          analyzed={data.header.analyzed_jobs}
        />
      ))}
    </div>
  )
}

function ExperienceArrangement({
  data,
  filters,
}: {
  data: AnalysisData
  filters: JobFilters
}) {
  return (
    <div className="skl-two">
      <DistributionPanel
        title="Experience level"
        buckets={data.experience_levels}
        labels={LEVEL_LABELS}
        linkFor={(value) =>
          value === 'unspecified'
            ? null
            : searchUrl({
                ...filters,
                experience_level: value as JobFilters['experience_level'],
              })
        }
      />
      <DistributionPanel
        title="Work arrangement"
        buckets={data.arrangements}
        linkFor={(value) =>
          value === 'unspecified'
            ? null
            : searchUrl({ ...filters, arrangement: value as JobFilters['arrangement'] })
        }
      />
    </div>
  )
}

function DistributionPanel({
  title,
  buckets,
  labels,
  linkFor,
}: {
  title: string
  buckets: DistributionBucket[]
  labels?: Record<string, string>
  linkFor: (value: string) => string | null
}) {
  if (buckets.length === 0) return null
  return (
    <div className="panel skl-dist">
      <h3 className="skl-card-title">{title}</h3>
      {buckets.map((bucket) => {
        const label = labels?.[bucket.value] ?? bucket.value
        const link = linkFor(bucket.value)
        return (
          <div key={bucket.value} className="skl-dist-row">
            <span className="skl-dist-row__label">
              {link ? <Link to={link}>{label}</Link> : label}
            </span>
            <span className="bar">
              <span className="bar__fill" style={{ width: `${bucket.share * 100}%` }} />
            </span>
            <span className="skl-dist-row__count">
              {bucket.count.toLocaleString()}{' '}
              <small>({Math.round(bucket.share * 100)}%)</small>
            </span>
          </div>
        )
      })}
    </div>
  )
}

function TopCompanies({ data }: { data: AnalysisData }) {
  const companies = data.top_companies
  if (companies.length === 0) {
    return <p className="muted skl-empty">No company data for this scope yet.</p>
  }
  const max = companies[0]?.count ?? 1
  return (
    <div className="panel skl-companies">
      <h3 className="skl-card-title">Top companies hiring</h3>
      <ol className="skl-company-list">
        {companies.map((company) => (
          <li key={company.name} className="skl-company-row">
            <span className="skl-company-row__name">{company.name}</span>
            <span className="bar">
              <span className="bar__fill" style={{ width: `${(company.count / max) * 100}%` }} />
            </span>
            <span className="skl-company-row__count">{company.count.toLocaleString()}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}

function SalaryInsights({ data }: { data: AnalysisData }) {
  const { salary, header } = data
  const salaryPct = Math.round((header.salary_disclosed / header.analyzed_jobs) * 100)

  if (salary.median === null || salary.p25 === null || salary.p75 === null) {
    return (
      <div className="panel skl-salary">
        <h3 className="skl-card-title">Salary insights</h3>
        <p className="muted">
          Not enough postings in this scope disclose salary to summarize pay. Try widening the
          radius or removing a filter.
        </p>
      </div>
    )
  }

  return (
    <div className="panel skl-salary">
      <h3 className="skl-card-title">Salary insights</h3>
      <div className="skl-salary__grid">
        <div className="skl-salary__stat">
          <strong>{fmtK(salary.median)}</strong>
          <span className="muted">Median disclosed salary</span>
        </div>
        <div className="skl-salary__stat">
          <strong>
            {fmtK(salary.p25)} – {fmtK(salary.p75)}
          </strong>
          <span className="muted">Middle 50% (25th–75th percentile)</span>
        </div>
        <div className="skl-salary__stat">
          <strong>{header.salary_disclosed.toLocaleString()}</strong>
          <span className="muted">Postings disclosing salary · {salaryPct}% of total</span>
        </div>
      </div>
      <p className="hint">
        Percentiles are computed only over postings that disclose pay — undisclosed salaries are
        excluded, not assumed.
      </p>
    </div>
  )
}

/* ── Skeleton ─────────────────────────────────────────────────────────── */

function SkillsSkeleton() {
  return (
    <div aria-busy="true">
      <div className="stat-tiles">
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className="skeleton stat-tile stat-tile--skeleton" />
        ))}
      </div>
      <div className="cat-grid">
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className="skeleton skeleton-card" />
        ))}
      </div>
    </div>
  )
}
