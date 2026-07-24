import { Link, useParams, useSearchParams } from 'react-router-dom'

import { ApiError, isAuthError } from '../../shared/api/client'
import { useMeta } from '../../shared/api/queries'
import type {
  JobMatch,
  MatchProfileSummary,
  MatchSkill,
  MatchWeights,
  ScoreComponent,
} from '../../shared/api/types'
import {
  fromSearchParams,
  toSearchParams,
  RADIUS_OPTIONS,
  type JobFilters,
} from '../../shared/filters'
import { useProfile, useProfileMatches } from './api'
import { AuthNotice } from '../auth/AuthNotice'

const LEVEL_LABELS: Record<string, string> = {
  entry: 'Entry',
  mid: 'Mid',
  senior: 'Senior',
  staff_plus: 'Staff+',
}

const DEGREE_LABELS: Record<string, string> = {
  associate: "Associate's",
  bachelor: "Bachelor's",
  master: "Master's",
  doctorate: 'Doctorate',
}

const ARRANGEMENTS = ['onsite', 'hybrid', 'remote'] as const

/**
 * /profile/:id/matches — rank active jobs against a reviewed profile (M9).
 * Every score is explained: the reasons, the matched and missing skills,
 * and the weighted component breakdown that produced it, so the ranking is
 * legible rather than an opaque number. The candidate pool is drawn through
 * the same shared filter scope the market surface uses, so a user can
 * narrow matches to, e.g., remote senior roles in one metro.
 */
export function MatchesPage() {
  const { id } = useParams()
  const profileId = Number(id)
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = fromSearchParams(searchParams)
  const { data: meta } = useMeta()
  const { data: profile } = useProfile(profileId)
  const query = useProfileMatches(profileId, filters)

  const update = (next: JobFilters) => setSearchParams(toSearchParams(next))

  const backLink = (
    <Link to={`/profile/${profileId}`} className="matches-back">
      ← Back to profile
    </Link>
  )

  if (query.isPending) {
    return (
      <section className="matches-page">
        {backLink}
        <div className="skeleton skeleton-header" />
        <div className="skeleton skeleton-card" />
      </section>
    )
  }

  if (isAuthError(query.error)) {
    return (
      <section className="matches-page">
        {backLink}
        <h2>Job matches</h2>
        <AuthNotice error={query.error} />
      </section>
    )
  }

  const status = query.error instanceof ApiError ? query.error.status : undefined
  if (status === 409) {
    return (
      <section className="matches-page">
        {backLink}
        <h2>Job matches</h2>
        <p className="banner">
          This profile hasn&rsquo;t been reviewed yet. Matching only ever uses a profile you
          have confirmed — <Link to={`/profile/${profileId}`}>review and confirm it</Link> to
          see matches.
        </p>
      </section>
    )
  }
  if (status === 404) {
    return (
      <section className="matches-page">
        {backLink}
        <p>Profile not found.</p>
      </section>
    )
  }
  if (query.isError || !query.data) {
    return (
      <section className="matches-page">
        {backLink}
        <p>Could not load matches. Is the backend running?</p>
      </section>
    )
  }

  const { data } = query
  const heading = profile?.full_name ?? data.profile.full_name ?? 'this profile'

  return (
    <section className="matches-page">
      {backLink}
      <h2>Job matches for {heading}</h2>
      <p className="muted">
        Ranked deterministically against your reviewed profile — skills, role family, and
        experience — over{' '}
        {data.total_active_jobs.toLocaleString()} active {scopeLabel(filters)}. Every score
        shows exactly why it ranks where it does.
      </p>

      <ProfileContext profile={data.profile} weights={data.weights} />
      <ScopeControls filters={filters} meta={meta} onChange={update} />

      <p className="muted matches-count">
        {data.matched_jobs === 0
          ? 'No jobs share a skill or role signal with this profile in this scope.'
          : `${data.matched_jobs.toLocaleString()} matching ${
              data.matched_jobs === 1 ? 'job' : 'jobs'
            }` +
            (data.returned < data.matched_jobs
              ? ` · showing the top ${data.returned.toLocaleString()}`
              : '')}
      </p>

      {data.matched_jobs === 0 ? (
        <EmptyState profile={data.profile} hasScope={Object.keys(filters).length > 0} />
      ) : (
        <ol className="match-list">
          {data.matches.map((match) => (
            <MatchCard key={match.job.id} match={match} />
          ))}
        </ol>
      )}
    </section>
  )
}

function scopeLabel(filters: JobFilters): string {
  return Object.keys(filters).length > 0 ? 'jobs in this scope' : 'jobs nationwide'
}

/** The candidate side of the match: what actually drives the ranking, and
 * an honest note about skills that cannot join the taxonomy. */
function ProfileContext({
  profile,
  weights,
}: {
  profile: MatchProfileSummary
  weights: MatchWeights
}) {
  const facts: string[] = []
  if (profile.experience_level) {
    let level = LEVEL_LABELS[profile.experience_level] ?? profile.experience_level
    if (profile.years_experience != null) level += ` · ${profile.years_experience} yrs`
    facts.push(level)
  }
  if (profile.highest_degree) {
    facts.push(DEGREE_LABELS[profile.highest_degree] ?? profile.highest_degree)
  }

  return (
    <div className="match-context">
      <div className="match-context__facts">
        <span className="fact">{profile.matched_skill_count} skills matched to taxonomy</span>
        {profile.title_families.map((family) => (
          <span key={family} className="fact">
            {family}
          </span>
        ))}
        {facts.map((f) => (
          <span key={f} className="fact fact--muted">
            {f}
          </span>
        ))}
      </div>
      {profile.unmapped_skill_count > 0 && (
        <p className="hint">
          {profile.unmapped_skill_count} skill{profile.unmapped_skill_count === 1 ? '' : 's'} on
          your profile {profile.unmapped_skill_count === 1 ? 'is' : 'are'} outside the taxonomy
          and can&rsquo;t be matched against jobs.
        </p>
      )}
      <p className="hint">
        Weighting: skills {Math.round(weights.skills * 100)}%, role family{' '}
        {Math.round(weights.title * 100)}%, experience {Math.round(weights.experience * 100)}% —
        components a job doesn&rsquo;t specify are dropped and the rest re-weighted.
      </p>
    </div>
  )
}

/** A compact scope control. Reuses the shared URL filter dialect (no
 * matching or filtering logic of its own) so the candidate pool narrows the
 * exact way the job-search predicate does. No sort — matches rank by score. */
function ScopeControls({
  filters,
  meta,
  onChange,
}: {
  filters: JobFilters
  meta: ReturnType<typeof useMeta>['data']
  onChange: (next: JobFilters) => void
}) {
  const hasScope = Object.keys(filters).length > 0
  return (
    <div className="scope-controls match-scope">
      <label>
        Location
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
      </label>
      {filters.location && (
        <label>
          Radius
          <select
            value={filters.radius_miles ?? 50}
            onChange={(e) => onChange({ ...filters, radius_miles: Number(e.target.value) })}
          >
            {RADIUS_OPTIONS.map((r) => (
              <option key={r} value={r}>
                {r} mi
              </option>
            ))}
          </select>
        </label>
      )}
      <label>
        Arrangement
        <select
          value={filters.arrangement ?? ''}
          onChange={(e) =>
            onChange({
              ...filters,
              arrangement: (e.target.value || undefined) as JobFilters['arrangement'],
            })
          }
        >
          <option value="">Any</option>
          {ARRANGEMENTS.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>
      </label>
      <label>
        Experience
        <select
          value={filters.experience_level ?? ''}
          onChange={(e) =>
            onChange({
              ...filters,
              experience_level: (e.target.value ||
                undefined) as JobFilters['experience_level'],
            })
          }
        >
          <option value="">Any</option>
          {(['entry', 'mid', 'senior', 'staff_plus'] as const).map((l) => (
            <option key={l} value={l}>
              {LEVEL_LABELS[l]}
            </option>
          ))}
        </select>
      </label>
      <label>
        Min salary
        <select
          value={filters.salary_min ?? ''}
          onChange={(e) =>
            onChange({ ...filters, salary_min: e.target.value ? Number(e.target.value) : undefined })
          }
        >
          <option value="">Any</option>
          {[100_000, 150_000, 200_000, 250_000].map((v) => (
            <option key={v} value={v}>
              ${v / 1000}k+
            </option>
          ))}
        </select>
      </label>
      {hasScope && (
        <button className="clear-scope" onClick={() => onChange({})}>
          Clear scope
        </button>
      )}
    </div>
  )
}

function scoreBand(score: number): string {
  if (score >= 80) return 'strong'
  if (score >= 60) return 'good'
  if (score >= 40) return 'fair'
  return 'weak'
}

function MatchCard({ match }: { match: JobMatch }) {
  const { job } = match
  return (
    <li className="match-card">
      <div className={`match-score match-score--${scoreBand(match.score)}`}>
        <strong>{match.score}</strong>
        <small>match</small>
      </div>
      <div className="match-body">
        <div className="match-head">
          <Link to={`/jobs/${job.id}`} className="match-title">
            {job.title_raw}
          </Link>
          <span className="muted"> — {job.company_name}</span>
        </div>
        <div className="job-facts">
          {job.canonical_title && <span className="fact">{job.canonical_title}</span>}
          {job.experience_level && (
            <span className="fact">{LEVEL_LABELS[job.experience_level] ?? job.experience_level}</span>
          )}
          {job.arrangement && <span className="fact">{job.arrangement}</span>}
          {job.locations.map((loc) => (
            <span key={loc.raw_text} className="fact fact--muted">
              {loc.raw_text}
            </span>
          ))}
        </div>
        <SalaryLine salary={job.salary} />

        {match.reasons.length > 0 && (
          <ul className="match-reasons">
            {match.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        )}

        <SkillLists matched={match.matched_skills} missing={match.missing_skills} />

        <details className="match-breakdown">
          <summary>Why this score</summary>
          <div className="match-components">
            {match.components.map((component) => (
              <ComponentRow key={component.key} component={component} />
            ))}
          </div>
        </details>

        {job.apply_url && (
          <a className="match-apply" href={job.apply_url} target="_blank" rel="noreferrer">
            View original posting →
          </a>
        )}
      </div>
    </li>
  )
}

function ComponentRow({ component }: { component: ScoreComponent }) {
  const pct = component.score == null ? null : Math.round(component.score * 100)
  return (
    <div className={`match-component${component.applicable ? '' : ' match-component--na'}`}>
      <span className="match-component__label">
        {component.label}
        <small> · {Math.round(component.weight * 100)}%</small>
      </span>
      <div className="dist-bar">
        {pct != null && (
          <div className={`dist-fill match-fill--${component.key}`} style={{ width: `${pct}%` }} />
        )}
      </div>
      <span className="match-component__value">
        {component.applicable ? `+${component.contribution.toFixed(1)}` : 'n/a'}
      </span>
      <span className="match-component__detail">{component.detail}</span>
    </div>
  )
}

function SkillLists({ matched, missing }: { matched: MatchSkill[]; missing: MatchSkill[] }) {
  if (matched.length === 0 && missing.length === 0) return null
  return (
    <div className="match-skills">
      {matched.length > 0 && (
        <div className="match-skills__group">
          <h4>You have</h4>
          <div className="skill-chips">
            {matched.map((skill) => (
              <SkillPill key={skill.slug} skill={skill} />
            ))}
          </div>
        </div>
      )}
      {missing.length > 0 && (
        <div className="match-skills__group">
          <h4>Gaps</h4>
          <div className="skill-chips">
            {missing.map((skill) => (
              <SkillPill key={skill.slug} skill={skill} missing />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function SkillPill({ skill, missing }: { skill: MatchSkill; missing?: boolean }) {
  return (
    <Link
      to={`/skills/${skill.slug}`}
      className={`skill-chip skill-chip--${skill.requirement_level}${
        missing ? ' skill-chip--gap' : ''
      }`}
      title={`${skill.requirement_level}${missing ? ' — not on your profile' : ''}`}
    >
      {skill.name}
    </Link>
  )
}

function SalaryLine({ salary }: { salary: JobMatch['job']['salary'] }) {
  if (!salary.annual_min) return null
  const fmt = (v: string) => `$${Math.round(Number(v)).toLocaleString()}`
  const sameEnds = salary.annual_max === salary.annual_min
  return (
    <p className="salary-line">
      {salary.period === 'hour' ? (
        <>
          ${Number(salary.min_amount)}–${Number(salary.max_amount)}/hour
          <small>
            {' '}
            (≈ {fmt(salary.annual_min)}
            {!sameEnds && salary.annual_max && <>–{fmt(salary.annual_max)}</>} annually)
          </small>
        </>
      ) : (
        <>
          {fmt(salary.annual_min)}
          {!sameEnds && salary.annual_max && <>–{fmt(salary.annual_max)}</>} per year
        </>
      )}
    </p>
  )
}

function EmptyState({
  profile,
  hasScope,
}: {
  profile: MatchProfileSummary
  hasScope: boolean
}) {
  if (profile.matched_skill_count === 0 && profile.title_families.length === 0) {
    return (
      <p className="muted">
        This profile has no taxonomy-mapped skills or recognised role families to match on. Add
        skills the taxonomy knows, or confirm an experience with a canonical title, then try
        again.
      </p>
    )
  }
  return (
    <p className="muted">
      No active jobs share a skill or role family with this profile
      {hasScope ? ' in this scope — try widening it.' : '.'}
    </p>
  )
}
