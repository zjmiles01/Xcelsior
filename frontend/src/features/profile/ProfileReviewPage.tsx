import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { ApiError, isAuthError } from '../../shared/api/client'
import {
  useDeleteProfile,
  useProfile,
  useReextractProfile,
  useUpdateProfile,
  type ProfileDetail,
  type ProfileUpdate,
} from './api'
import { AuthNotice } from '../auth/AuthNotice'

/**
 * /profile/:id — review and edit the extracted profile. Save sends the
 * whole edited document (full-document PUT reconcile); "Save & confirm"
 * additionally marks it reviewed — the gate future consumers respect.
 * Every extracted fact shows its confidence and evidence, so accepting
 * or deleting it is an informed call, not a guess.
 */

type SkillRow = {
  key: string
  id?: number
  label: string
  confidence: number | null
  evidence: string | null
  origin: string
}

type ExperienceRow = {
  key: string
  id?: number
  title_raw: string
  company: string
  start_date: string
  end_date: string
  is_current: boolean
  summary: string
  origin: string
}

type EducationRow = {
  key: string
  id?: number
  institution: string
  degree_raw: string
  field_of_study: string
  start_year: string
  end_year: string
  origin: string
}

let nextKey = 0
const freshKey = () => `new-${nextKey++}`

function rowsFromProfile(profile: ProfileDetail) {
  return {
    skills: profile.skills.map((s) => ({
      key: `s-${s.id}`,
      id: s.id,
      label: s.label,
      confidence: s.confidence ?? null,
      evidence: s.evidence_snippet ?? null,
      origin: s.origin,
    })),
    experiences: profile.experiences.map((e) => ({
      key: `e-${e.id}`,
      id: e.id,
      title_raw: e.title_raw,
      company: e.company ?? '',
      start_date: e.start_date ?? '',
      end_date: e.end_date ?? '',
      is_current: e.is_current,
      summary: e.summary ?? '',
      origin: e.origin,
    })),
    education: profile.education.map((e) => ({
      key: `d-${e.id}`,
      id: e.id,
      institution: e.institution ?? '',
      degree_raw: e.degree_raw ?? '',
      field_of_study: e.field_of_study ?? '',
      start_year: e.start_year?.toString() ?? '',
      end_year: e.end_year?.toString() ?? '',
      origin: e.origin,
    })),
  }
}

export function ProfileReviewPage() {
  const { id } = useParams()
  const profileId = Number(id)
  const navigate = useNavigate()
  const { data: profile, isPending, isError, error } = useProfile(profileId)
  const update = useUpdateProfile(profileId)
  const reextract = useReextractProfile(profileId)
  const remove = useDeleteProfile(profileId)

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [skills, setSkills] = useState<SkillRow[]>([])
  const [experiences, setExperiences] = useState<ExperienceRow[]>([])
  const [education, setEducation] = useState<EducationRow[]>([])
  const [newSkill, setNewSkill] = useState('')

  // Re-initialize whenever the server document changes (fetch, save,
  // re-extract): the server copy is always the base of the next edit.
  useEffect(() => {
    if (!profile) return
    setFullName(profile.full_name ?? '')
    setEmail(profile.email ?? '')
    setPhone(profile.phone ?? '')
    const rows = rowsFromProfile(profile)
    setSkills(rows.skills)
    setExperiences(rows.experiences)
    setEducation(rows.education)
  }, [profile])

  const payload = useMemo(
    (): ProfileUpdate => ({
      full_name: fullName || null,
      email: email || null,
      phone: phone || null,
      reviewed: false,
      skills: skills.map((s) => (s.id !== undefined ? { id: s.id } : { label: s.label })),
      experiences: experiences.map((e) => ({
        ...(e.id !== undefined ? { id: e.id } : {}),
        title_raw: e.title_raw,
        company: e.company || null,
        start_date: e.start_date || null,
        end_date: e.is_current ? null : e.end_date || null,
        is_current: e.is_current,
        summary: e.summary || null,
      })),
      education: education.map((e) => ({
        ...(e.id !== undefined ? { id: e.id } : {}),
        institution: e.institution || null,
        degree_raw: e.degree_raw || null,
        field_of_study: e.field_of_study || null,
        start_year: e.start_year ? Number(e.start_year) : null,
        end_year: e.end_year ? Number(e.end_year) : null,
      })),
    }),
    [fullName, email, phone, skills, experiences, education],
  )

  if (isPending) return <p>Loading profile…</p>
  if (isAuthError(error)) return <AuthNotice error={error} />
  if (isError || !profile) return <p>Profile not found.</p>

  const save = (reviewed: boolean) => update.mutate({ ...payload, reviewed })

  const addSkill = () => {
    const label = newSkill.trim()
    if (!label) return
    setSkills((rows) => [...rows, { key: freshKey(), label, confidence: null, evidence: null, origin: 'manual' }])
    setNewSkill('')
  }

  return (
    <article className="profile-review">
      <Link to="/profile">← All profiles</Link>
      <header className="dashboard-header">
        <h2>{profile.full_name ?? profile.resume.filename}</h2>
        {profile.reviewed_at ? (
          <span className="profile-review__status">
            <span className="fact">Reviewed</span>
            <Link to={`/profile/${profileId}/matches`} className="btn btn--primary btn--small">
              Find matching jobs →
            </Link>
          </span>
        ) : (
          <span className="fact fact--muted">Awaiting review</span>
        )}
      </header>
      <p className="muted">
        Extracted from {profile.resume.filename} — review each fact, fix what the
        extractor got wrong, then confirm. Saving an edit marks that fact as yours.
      </p>

      <section className="edit-card">
        <h3>Contact</h3>
        <div className="field-grid">
          <label>
            Name
            <input value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </label>
          <label>
            Email
            <input value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label>
            Phone
            <input value={phone} onChange={(e) => setPhone(e.target.value)} />
          </label>
        </div>
      </section>

      <section className="edit-card">
        <h3>Skills</h3>
        <div className="skill-chips">
          {skills.map((skill) => (
            <span
              key={skill.key}
              className="skill-chip"
              title={
                skill.evidence
                  ? `“${skill.evidence}”${skill.confidence != null ? ` · confidence ${Math.round(skill.confidence * 100)}%` : ''}`
                  : 'Added manually'
              }
            >
              {skill.label}
              {skill.confidence != null && (
                <small className="confidence"> {Math.round(skill.confidence * 100)}%</small>
              )}
              <button
                type="button"
                className="chip-remove"
                aria-label={`Remove ${skill.label}`}
                onClick={() => setSkills((rows) => rows.filter((r) => r.key !== skill.key))}
              >
                ×
              </button>
            </span>
          ))}
        </div>
        <div className="add-row">
          <input
            placeholder="Add a skill…"
            value={newSkill}
            onChange={(e) => setNewSkill(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                addSkill()
              }
            }}
          />
          <button type="button" className="btn" onClick={addSkill}>
            Add
          </button>
        </div>
      </section>

      <section className="edit-card">
        <h3>Experience</h3>
        {experiences.map((exp, i) => (
          <ExperienceEditor
            key={exp.key}
            row={exp}
            onChange={(next) =>
              setExperiences((rows) => rows.map((r, j) => (j === i ? next : r)))
            }
            onRemove={() => setExperiences((rows) => rows.filter((_, j) => j !== i))}
          />
        ))}
        <button
          type="button"
          className="btn"
          onClick={() =>
            setExperiences((rows) => [
              ...rows,
              {
                key: freshKey(),
                title_raw: '',
                company: '',
                start_date: '',
                end_date: '',
                is_current: false,
                summary: '',
                origin: 'manual',
              },
            ])
          }
        >
          Add experience
        </button>
      </section>

      <section className="edit-card">
        <h3>Education</h3>
        {education.map((edu, i) => (
          <EducationEditor
            key={edu.key}
            row={edu}
            onChange={(next) => setEducation((rows) => rows.map((r, j) => (j === i ? next : r)))}
            onRemove={() => setEducation((rows) => rows.filter((_, j) => j !== i))}
          />
        ))}
        <button
          type="button"
          className="btn"
          onClick={() =>
            setEducation((rows) => [
              ...rows,
              {
                key: freshKey(),
                institution: '',
                degree_raw: '',
                field_of_study: '',
                start_year: '',
                end_year: '',
                origin: 'manual',
              },
            ])
          }
        >
          Add education
        </button>
      </section>

      {update.isError && (
        <p className="banner">
          {update.error instanceof ApiError ? update.error.message : 'Save failed.'}
        </p>
      )}

      <div className="profile-toolbar">
        <button
          type="button"
          className="btn btn--primary"
          disabled={update.isPending}
          onClick={() => save(true)}
        >
          Save &amp; confirm profile
        </button>
        <button type="button" className="btn" disabled={update.isPending} onClick={() => save(false)}>
          Save draft
        </button>
        <span className="toolbar-spacer" />
        <button
          type="button"
          className="btn"
          disabled={reextract.isPending}
          onClick={() => {
            if (window.confirm('Re-extract from the resume text? All edits will be discarded.')) {
              reextract.mutate()
            }
          }}
        >
          Re-extract
        </button>
        <button
          type="button"
          className="btn btn--danger"
          disabled={remove.isPending}
          onClick={() => {
            if (window.confirm('Delete this profile and its uploaded resume?')) {
              remove.mutate(undefined, { onSuccess: () => navigate('/profile') })
            }
          }}
        >
          Delete
        </button>
      </div>
    </article>
  )
}

function ExperienceEditor({
  row,
  onChange,
  onRemove,
}: {
  row: ExperienceRow
  onChange: (row: ExperienceRow) => void
  onRemove: () => void
}) {
  return (
    <div className="entry-editor">
      <div className="entry-editor__head">
        <span className={`origin-tag origin-tag--${row.origin}`}>{row.origin}</span>
        <button type="button" className="btn btn--danger btn--small" onClick={onRemove}>
          Remove
        </button>
      </div>
      <div className="field-grid">
        <label>
          Title
          <input value={row.title_raw} onChange={(e) => onChange({ ...row, title_raw: e.target.value })} />
        </label>
        <label>
          Company
          <input value={row.company} onChange={(e) => onChange({ ...row, company: e.target.value })} />
        </label>
        <label>
          Start
          <input
            type="date"
            value={row.start_date}
            onChange={(e) => onChange({ ...row, start_date: e.target.value })}
          />
        </label>
        <label>
          End
          <input
            type="date"
            value={row.end_date}
            disabled={row.is_current}
            onChange={(e) => onChange({ ...row, end_date: e.target.value })}
          />
        </label>
        <label className="field-check">
          <input
            type="checkbox"
            checked={row.is_current}
            onChange={(e) => onChange({ ...row, is_current: e.target.checked, end_date: '' })}
          />
          Current position
        </label>
      </div>
      <label>
        Notes
        <textarea
          rows={3}
          value={row.summary}
          onChange={(e) => onChange({ ...row, summary: e.target.value })}
        />
      </label>
    </div>
  )
}

function EducationEditor({
  row,
  onChange,
  onRemove,
}: {
  row: EducationRow
  onChange: (row: EducationRow) => void
  onRemove: () => void
}) {
  return (
    <div className="entry-editor">
      <div className="entry-editor__head">
        <span className={`origin-tag origin-tag--${row.origin}`}>{row.origin}</span>
        <button type="button" className="btn btn--danger btn--small" onClick={onRemove}>
          Remove
        </button>
      </div>
      <div className="field-grid">
        <label>
          Institution
          <input
            value={row.institution}
            onChange={(e) => onChange({ ...row, institution: e.target.value })}
          />
        </label>
        <label>
          Degree
          <input
            value={row.degree_raw}
            onChange={(e) => onChange({ ...row, degree_raw: e.target.value })}
          />
        </label>
        <label>
          Field of study
          <input
            value={row.field_of_study}
            onChange={(e) => onChange({ ...row, field_of_study: e.target.value })}
          />
        </label>
        <label>
          Start year
          <input
            inputMode="numeric"
            value={row.start_year}
            onChange={(e) => onChange({ ...row, start_year: e.target.value })}
          />
        </label>
        <label>
          End year
          <input
            inputMode="numeric"
            value={row.end_year}
            onChange={(e) => onChange({ ...row, end_year: e.target.value })}
          />
        </label>
      </div>
    </div>
  )
}
