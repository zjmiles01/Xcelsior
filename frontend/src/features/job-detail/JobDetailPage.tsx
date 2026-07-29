import { Link, useParams } from 'react-router-dom'

import { SaveJobButton } from '../saved/SaveJobButton'
import { useJobDetail, type JobDetail, type JobTechnology } from './api'
import { SkillChip } from './SkillChip'

const LEVEL_LABELS: Record<string, string> = {
  required: 'Required skills',
  preferred: 'Nice to have',
  mentioned: 'Also mentioned',
}

const EXPERIENCE_LABELS: Record<string, string> = {
  entry: 'Entry level',
  mid: 'Mid level',
  senior: 'Senior',
  staff_plus: 'Staff+',
}

const EMPLOYMENT_TYPE_LABELS: Record<string, string> = {
  full_time: 'Full-time',
  part_time: 'Part-time',
  internship: 'Internship',
  contract: 'Contract',
  temporary: 'Temporary',
}

export function JobDetailPage() {
  const { id } = useParams()
  const { data: job, isPending, isError } = useJobDetail(Number(id))

  if (isPending) return <p>Loading job…</p>
  if (isError || !job) return <p>Job not found.</p>

  return (
    <article className="job-detail">
      <Link to="/jobs">← All jobs</Link>
      <header>
        <div className="job-detail__title">
          <h2>{job.title_raw}</h2>
          <SaveJobButton jobId={job.id} />
        </div>
        <div className="job-facts">
          <strong>{job.company_name}</strong>
          {job.canonical_title && <span className="fact">{job.canonical_title}</span>}
          {job.experience_level && (
            <span className="fact">{EXPERIENCE_LABELS[job.experience_level]}</span>
          )}
          {job.arrangement && <span className="fact">{job.arrangement}</span>}
          {job.employment_type && job.employment_type !== 'unknown' && (
            <span className="fact">
              {EMPLOYMENT_TYPE_LABELS[job.employment_type] ?? job.employment_type}
            </span>
          )}
          {job.locations.map((loc) => (
            <span key={loc.raw_text} className="fact fact--muted">
              {loc.raw_text}
            </span>
          ))}
        </div>
        <SalaryLine job={job} />
        {job.status === 'expired' && (
          <p className="banner">
            This posting is no longer active — analysis is preserved for reference.
          </p>
        )}
      </header>

      <TechnologyGroups technologies={job.technologies} />

      <Description job={job} />
      {!job.description_text && !job.description_html && (
        <p>
          Full description available at the original posting
          {job.source.attribution_text && <> · via {job.source.attribution_text}</>}
        </p>
      )}

      {job.apply_url && job.status === 'active' && (
        <a className="apply-link" href={job.apply_url} target="_blank" rel="noreferrer">
          View original posting →
        </a>
      )}
    </article>
  )
}

function Description({ job }: { job: JobDetail }) {
  // description_html is sanitized server-side (nh3 allowlist, M8) — that is
  // the XSS guarantee this render relies on. Prefer it for rich formatting;
  // fall back to the flattened plain text when only that is available.
  if (job.description_html) {
    return (
      <section>
        <h3>Description</h3>
        <div
          className="job-description job-description--rich"
          dangerouslySetInnerHTML={{ __html: job.description_html }}
        />
      </section>
    )
  }
  if (job.description_text) {
    return (
      <section>
        <h3>Description</h3>
        <pre className="job-description">{job.description_text}</pre>
      </section>
    )
  }
  return null
}

function SalaryLine({ job }: { job: JobDetail }) {
  const { salary } = job
  if (!salary.annual_min) return null
  const fmt = (v: string) => `$${Math.round(Number(v)).toLocaleString()}`
  return (
    <p className="salary-line">
      {salary.period === 'hour' ? (
        <>
          ${Number(salary.min_amount)}–${Number(salary.max_amount)}/hour
          <small>
            {' '}
            (≈ {fmt(salary.annual_min!)}–{fmt(salary.annual_max!)} annually)
          </small>
        </>
      ) : (
        <>
          {fmt(salary.annual_min!)}
          {salary.annual_max !== salary.annual_min && <>–{fmt(salary.annual_max!)}</>} per year
        </>
      )}
      <small> · as stated in posting</small>
    </p>
  )
}

function TechnologyGroups({ technologies }: { technologies: JobTechnology[] }) {
  if (technologies.length === 0) return null
  const groups = (['required', 'preferred', 'mentioned'] as const)
    .map((level) => ({
      level,
      items: technologies.filter((t) => t.requirement_level === level),
    }))
    .filter((g) => g.items.length > 0)

  return (
    <section>
      <h3>Technologies</h3>
      <p className="hint">Hover a skill to see the sentence it was extracted from.</p>
      {groups.map((group) => (
        <div key={group.level} className="skill-group">
          <h4>{LEVEL_LABELS[group.level]}</h4>
          <div className="skill-chips">
            {group.items.map((tech) => (
              <SkillChip key={tech.slug} tech={tech} />
            ))}
          </div>
        </div>
      ))}
    </section>
  )
}
