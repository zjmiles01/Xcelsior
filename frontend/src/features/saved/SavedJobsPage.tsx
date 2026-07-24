import { Link } from 'react-router-dom'

import type { MatchSkill, SavedJobMatch, SavedJobOut } from '../../shared/api/types'
import { AuthNotice } from '../auth/AuthNotice'
import { useSavedJobs, useUnsaveJob } from './api'

const LEVEL_LABELS: Record<string, string> = {
  entry: 'Entry',
  mid: 'Mid',
  senior: 'Senior',
  staff_plus: 'Staff+',
}

/**
 * /saved — the saved-jobs dashboard (M10). Not a bookmark list: each saved
 * job shows how close the user is to qualifying, computed live against their
 * most recently reviewed profile — score, matched skills, gaps — with a link
 * back to the full M9 explanation. The match info always reflects the current
 * profile, never a snapshot from when the job was saved.
 */
export function SavedJobsPage() {
  const query = useSavedJobs()

  if (query.isPending) {
    return (
      <section className="saved-page">
        <h2>Saved jobs</h2>
        <div className="skeleton skeleton-card" />
      </section>
    )
  }

  if (query.isError) {
    return (
      <section className="saved-page">
        <h2>Saved jobs</h2>
        <AuthNotice error={query.error} />
        {/* Non-auth failure */}
        <p className="muted">Could not load your saved jobs. Is the backend running?</p>
      </section>
    )
  }

  const { data } = query
  const profileId = data.profile_id

  return (
    <section className="saved-page">
      <h2>Saved jobs</h2>
      <p className="muted">
        Jobs you&rsquo;re tracking, each scored against your reviewed profile so you can see how
        close you are to qualifying — not just a bookmark.
      </p>

      {data.profile == null && (
        <p className="banner">
          Upload and review a resume to see how you match these jobs.{' '}
          <Link to="/profile">Build your profile →</Link>
        </p>
      )}

      {data.items.length === 0 ? (
        <p className="muted">
          You haven&rsquo;t saved any jobs yet. Browse <Link to="/jobs">jobs</Link> and use{' '}
          <strong>☆ Save</strong> to track the ones you care about.
        </p>
      ) : (
        <ol className="match-list">
          {data.items.map((item) => (
            <SavedCard key={item.job.id} item={item} profileId={profileId} />
          ))}
        </ol>
      )}
    </section>
  )
}

function scoreBand(score: number): string {
  if (score >= 80) return 'strong'
  if (score >= 60) return 'good'
  if (score >= 40) return 'fair'
  return 'weak'
}

function SavedCard({ item, profileId }: { item: SavedJobOut; profileId: number | null }) {
  const { job, match } = item
  const unsave = useUnsaveJob()

  return (
    <li className="match-card">
      {match ? (
        <div className={`match-score match-score--${scoreBand(match.score)}`}>
          <strong>{match.score}</strong>
          <small>match</small>
        </div>
      ) : (
        <div className="match-score match-score--na">
          <strong>—</strong>
          <small>no profile</small>
        </div>
      )}
      <div className="match-body">
        <div className="match-head">
          <Link to={`/jobs/${job.id}`} className="match-title">
            {job.title_raw}
          </Link>
          <span className="muted"> — {job.company_name}</span>
          <button
            type="button"
            className="btn btn--link saved-remove"
            onClick={() => unsave.mutate(job.id)}
            disabled={unsave.isPending}
          >
            Remove
          </button>
        </div>
        <div className="job-facts">
          {job.canonical_title && <span className="fact">{job.canonical_title}</span>}
          {job.experience_level && (
            <span className="fact">
              {LEVEL_LABELS[job.experience_level] ?? job.experience_level}
            </span>
          )}
          {job.arrangement && <span className="fact">{job.arrangement}</span>}
          {job.locations.map((loc) => (
            <span key={loc.raw_text} className="fact fact--muted">
              {loc.raw_text}
            </span>
          ))}
        </div>

        {match ? (
          <MatchSummary match={match} jobId={job.id} profileId={profileId} />
        ) : (
          <p className="hint">
            Review your profile to see how your skills line up with this role.
          </p>
        )}
      </div>
    </li>
  )
}

function MatchSummary({
  match,
  jobId,
  profileId,
}: {
  match: SavedJobMatch
  jobId: number
  profileId: number | null
}) {
  return (
    <>
      {match.reasons.length > 0 && (
        <ul className="match-reasons">
          {match.reasons.slice(0, 3).map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
      <SkillLists matched={match.matched_skills} missing={match.missing_skills} />
      {profileId != null && (
        <Link className="match-apply" to={`/profile/${profileId}/matches#job-${jobId}`}>
          See the full explanation →
        </Link>
      )}
    </>
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
