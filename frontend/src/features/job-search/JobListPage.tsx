import { Link, useSearchParams } from 'react-router-dom'

import { useMeta } from '../../shared/api/queries'
import type {
  AnalysisResponse,
  FacetBucket,
  JobListItem,
  RelaxationOption,
} from '../../shared/api/types'
import { relativeTimeSince } from '../../shared/format/time'
import {
  fromApiFilters,
  fromSearchParams,
  searchUrl,
  skillUrl,
  toSearchParams,
  type JobFilters,
  type SortOption,
} from '../../shared/filters'
import { useAnalysis } from '../dashboard/api'
import { SaveJobButton } from '../saved/SaveJobButton'
import { useJobSearch } from './api'
import { FilterPanel } from './FilterPanel'

const PAGE_SIZE = 25

const LEVEL_LABELS: Record<string, string> = {
  entry: 'Entry',
  mid: 'Mid',
  senior: 'Senior',
  staff_plus: 'Staff+',
  unspecified: 'Unspecified',
}

const ARRANGEMENT_LABELS: Record<string, string> = {
  onsite: 'Onsite',
  hybrid: 'Hybrid',
  remote: 'Remote',
  unspecified: 'Unspecified',
}

export function JobListPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = fromSearchParams(searchParams)
  const sort = (searchParams.get('sort') as SortOption) || 'recency'
  const { data: meta } = useMeta()
  const query = useJobSearch({ ...filters, sort, limit: PAGE_SIZE })

  function update(next: JobFilters, nextSort: SortOption = sort) {
    // Relevance sort is meaningless without keywords; fall back rather
    // than send a query the server will (rightly) refuse.
    const effective = nextSort === 'relevance' && !next.q ? 'recency' : nextSort
    setSearchParams(toSearchParams({ ...next, sort: effective === 'recency' ? undefined : effective }))
  }

  const first = query.data?.pages[0]
  const items = query.data?.pages.flatMap((page) => page.items) ?? []

  return (
    <section className="jobs">
      <header className="jobs-hero">
        <span className="eyebrow eyebrow--pill">Find relevant jobs</span>
        <h1 className="jobs-hero__title">Search jobs backed by real market data.</h1>
        <p className="jobs-hero__lead">
          Find opportunities that match your skills, experience, and career goals.
        </p>
      </header>

      <FilterPanel filters={filters} meta={meta} onChange={update} />

      {query.isError ? (
        <p className="banner jobs-status">Could not load jobs. Is the backend running?</p>
      ) : query.isPending || !first ? (
        <JobsSkeleton />
      ) : (
        <>
          <div className="jobs-results__head">
            <p className="jobs-results__count">
              {first.total === 0
                ? 'No jobs found'
                : `${first.total.toLocaleString()} jobs found`}
            </p>
            <label className="sortby">
              Sort by
              <select
                value={sort}
                onChange={(e) => update(filters, e.target.value as SortOption)}
              >
                <option value="recency">Most recent</option>
                <option value="salary">Highest salary</option>
                <option value="relevance" disabled={!filters.q}>
                  Relevance{filters.q ? '' : ' (needs keywords)'}
                </option>
              </select>
            </label>
          </div>

          {first.total === 0 ? (
            <Relaxations options={first.relaxations} />
          ) : (
            <div className="jobs-layout">
              <div className="jobs-col">
                <ul className="jobcards">
                  {items.map((job) => (
                    <li key={job.id}>
                      <JobCard job={job} />
                    </li>
                  ))}
                </ul>

                <div className="jobs-pager">
                  <p className="muted">
                    Showing {items.length.toLocaleString()} of {first.total.toLocaleString()}
                  </p>
                  {query.hasNextPage && (
                    <button
                      className="btn"
                      disabled={query.isFetchingNextPage}
                      onClick={() => query.fetchNextPage()}
                    >
                      {query.isFetchingNextPage ? 'Loading…' : 'Load more'}
                    </button>
                  )}
                </div>
              </div>

              <MarketOverview facets={first.facets} filters={filters} />
            </div>
          )}
        </>
      )}
    </section>
  )
}

/* ── Job card ─────────────────────────────────────────────────────────── */

function JobCard({ job }: { job: JobListItem }) {
  const primary = job.locations[0]?.raw_text ?? 'Location not specified'
  const isRemote = job.locations.some((l) => l.is_remote)
  const showRemote = isRemote && !/remote/i.test(primary)
  const avatar = companyAvatar(job.company_name)

  return (
    <article className="jobcard">
      <span className="jobcard__logo" style={{ background: avatar.bg, color: avatar.fg }}>
        {avatar.initial}
      </span>
      <div className="jobcard__main">
        <Link to={`/jobs/${job.id}`} className="jobcard__title">
          {job.title_raw}
        </Link>
        <p className="jobcard__company">{job.company_name}</p>
        <p className="jobcard__meta">
          {primary}
          {showRemote && <span className="jobcard__tag">Remote</span>}
        </p>
        {job.posted_at && (
          <p className="jobcard__posted">{relativeTimeSince(job.posted_at)}</p>
        )}
      </div>
      <SaveJobButton jobId={job.id} className="jobcard__save" />
    </article>
  )
}

/** A deterministic monogram for a company (no logo data in the API). Not a
 * brand mark — a stable, name-derived placeholder so cards scan quickly. */
function companyAvatar(name: string): { initial: string; bg: string; fg: string } {
  const palette = ['#2a2721', '#8a6a3b', '#3f7a4f', '#4f5d78', '#9a5a45', '#635686']
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0
  const bg = palette[hash % palette.length]
  const initial = name.trim().charAt(0).toUpperCase() || '?'
  return { initial, bg, fg: '#f7f4ec' }
}

/* ── Market overview sidebar ──────────────────────────────────────────── */

function MarketOverview({
  facets,
  filters,
}: {
  facets: { experience_levels: FacetBucket[]; arrangements: FacetBucket[] }
  filters: JobFilters
}) {
  const analysis = useAnalysis(filters)
  const query = toSearchParams(filters).toString()
  const skillsHref = query ? `/skills?${query}` : '/skills'

  return (
    <aside className="market">
      <div className="panel market__card">
        <div className="market__head">
          <div>
            <h3 className="market__title">Market overview</h3>
            <span className="market__sub">for these results</span>
          </div>
          <Link className="market__link" to={skillsHref}>
            View full analytics →
          </Link>
        </div>

        <MarketDistribution
          title="Experience level"
          buckets={facets.experience_levels}
          labels={LEVEL_LABELS}
          activeValue={filters.experience_level}
          linkFor={(value) =>
            value === 'unspecified'
              ? null
              : searchUrl({
                  ...filters,
                  experience_level:
                    filters.experience_level === value
                      ? undefined
                      : (value as JobFilters['experience_level']),
                })
          }
        />

        <MarketDistribution
          title="Work arrangement"
          buckets={facets.arrangements}
          labels={ARRANGEMENT_LABELS}
          activeValue={filters.arrangement}
          linkFor={(value) =>
            value === 'unspecified'
              ? null
              : searchUrl({
                  ...filters,
                  arrangement:
                    filters.arrangement === value
                      ? undefined
                      : (value as JobFilters['arrangement']),
                })
          }
        />
      </div>

      <TopSkillsCard analysis={analysis.data} filters={filters} skillsHref={skillsHref} />
      <SalaryCard analysis={analysis.data} />
    </aside>
  )
}

function MarketDistribution({
  title,
  buckets,
  labels,
  activeValue,
  linkFor,
}: {
  title: string
  buckets: FacetBucket[]
  labels: Record<string, string>
  activeValue?: string
  linkFor: (value: string) => string | null
}) {
  if (buckets.length === 0) return null
  return (
    <div className="market__section">
      <h4 className="market__section-title">{title}</h4>
      {buckets.map((bucket) => {
        const label = labels[bucket.value] ?? bucket.value
        const link = linkFor(bucket.value)
        const active = activeValue === bucket.value
        const row = (
          <>
            <span className="market-row__label">
              {label}
              {active && ' ✕'}
            </span>
            <span className="bar">
              <span className="bar__fill" style={{ width: `${bucket.share * 100}%` }} />
            </span>
            <span className="market-row__pct">{Math.round(bucket.share * 100)}%</span>
          </>
        )
        return link ? (
          <Link
            key={bucket.value}
            to={link}
            className={`market-row${active ? ' market-row--active' : ''}`}
          >
            {row}
          </Link>
        ) : (
          <div key={bucket.value} className="market-row market-row--static">
            {row}
          </div>
        )
      })}
    </div>
  )
}

function TopSkillsCard({
  analysis,
  filters,
  skillsHref,
}: {
  analysis: AnalysisResponse | undefined
  filters: JobFilters
  skillsHref: string
}) {
  const skills = analysis
    ? analysis.categories
        .flatMap((c) => c.technologies)
        .sort((a, b) => b.count - a.count)
        .slice(0, 8)
    : []

  return (
    <div className="panel market__card">
      <h3 className="market__title">Top skills in results</h3>
      {skills.length > 0 ? (
        <>
          <div className="market__chips">
            {skills.map((skill) => (
              <Link key={skill.slug} className="tech-pill" to={skillUrl(skill.slug, filters)}>
                {skill.name}
              </Link>
            ))}
          </div>
          <Link className="market__link" to={skillsHref}>
            View all skills →
          </Link>
        </>
      ) : (
        <p className="muted">No skill data for this scope yet.</p>
      )}
    </div>
  )
}

function SalaryCard({ analysis }: { analysis: AnalysisResponse | undefined }) {
  const fmtK = (n: number) => `$${Math.round(n / 1000)}K`
  const salary = analysis?.salary
  const disclosed = analysis?.header.salary_disclosed ?? 0

  return (
    <div className="panel market__card">
      <h3 className="market__title">Salary insights</h3>
      {salary && salary.median !== null && salary.p25 !== null && salary.p75 !== null ? (
        <>
          <p className="market__sub">Based on {disclosed.toLocaleString()} jobs with salary data</p>
          <p className="market-salary__median">{fmtK(salary.median)}</p>
          <p className="market-salary__range">
            {fmtK(salary.p25)} – {fmtK(salary.p75)} <span className="muted">middle 50%</span>
          </p>
        </>
      ) : (
        <p className="muted">Not enough postings disclose salary in this scope.</p>
      )}
    </div>
  )
}

/* ── Empty & loading states ───────────────────────────────────────────── */

/**
 * The server's honest way out of a zero-result search: each option says
 * exactly what it changes and how many jobs that yields. Nothing is
 * relaxed until the user clicks.
 */
function Relaxations({ options }: { options?: RelaxationOption[] }) {
  if (!options || options.length === 0) {
    return <p className="muted">Try removing a filter or widening the radius.</p>
  }
  return (
    <div>
      <p className="muted">Nearby searches that do match:</p>
      <ul className="relaxation-list">
        {options.map((option) => (
          <li key={option.kind + option.description}>
            <Link to={searchUrl(fromApiFilters(option.filters))}>{option.description}</Link>{' '}
            <span className="muted">({option.count.toLocaleString()} jobs)</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function JobsSkeleton() {
  return (
    <div className="jobs-layout" aria-busy="true">
      <div className="jobs-col">
        <ul className="jobcards">
          {Array.from({ length: 5 }, (_, i) => (
            <li key={i}>
              <div className="skeleton jobcard-skeleton" />
            </li>
          ))}
        </ul>
      </div>
      <aside className="market">
        <div className="skeleton skeleton-card" />
      </aside>
    </div>
  )
}
