import { useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError } from '../../shared/api/client'
import { useProfiles, useUploadResume } from './api'
import { AuthNotice } from '../auth/AuthNotice'

/**
 * /profile — upload a resume and list existing profiles. Upload runs the
 * whole deterministic pipeline synchronously and lands on the review
 * page, where nothing is "used elsewhere" until the user confirms it.
 */
export function ProfileListPage() {
  const navigate = useNavigate()
  const { data, isPending, error } = useProfiles()
  const upload = useUploadResume()
  const fileInput = useRef<HTMLInputElement>(null)

  const onFileChosen = (file: File | undefined) => {
    if (!file) return
    upload.mutate(file, {
      onSuccess: (profile) => navigate(`/profile/${profile.id}`),
    })
  }

  return (
    <section>
      <h2>Candidate profile</h2>
      <p className="muted">
        Upload a resume (PDF) to build a structured profile: skills, experience, and
        education, each traceable to the exact text it came from. Review and edit
        everything before it is used anywhere.
      </p>

      <AuthNotice error={error ?? upload.error} />

      <div className="profile-upload">
        <input
          ref={fileInput}
          type="file"
          accept="application/pdf,.pdf"
          style={{ display: 'none' }}
          onChange={(e) => onFileChosen(e.target.files?.[0])}
        />
        <button
          className="btn btn--primary"
          disabled={upload.isPending}
          onClick={() => fileInput.current?.click()}
        >
          {upload.isPending ? 'Extracting…' : 'Upload resume (PDF, max 5 MB)'}
        </button>
        {upload.isError && (
          <p className="banner">
            {upload.error instanceof ApiError ? upload.error.message : 'Upload failed.'}
          </p>
        )}
      </div>

      {isPending ? (
        <p>Loading profiles…</p>
      ) : data && data.items.length > 0 ? (
        <ul className="profile-list">
          {data.items.map((item) => (
            <li key={item.id}>
              <Link to={`/profile/${item.id}`}>
                <strong>{item.full_name ?? item.filename}</strong>
                <span className="job-meta">
                  {item.skill_count} skills · {item.experience_count} roles ·{' '}
                  {item.reviewed_at ? 'reviewed' : 'awaiting review'}
                </span>
              </Link>
              {item.reviewed_at && (
                <Link to={`/profile/${item.id}/matches`} className="profile-list__matches">
                  Find matching jobs →
                </Link>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">No profiles yet.</p>
      )}
    </section>
  )
}
