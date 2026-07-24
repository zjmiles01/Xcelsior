import { useLocation, useNavigate } from 'react-router-dom'

import { useCurrentUser } from '../auth/api'
import { useSaveJob, useSavedJobIds, useUnsaveJob } from './api'

/**
 * Save/Saved toggle for a job (M10). Saving is an authenticated action: an
 * anonymous visitor is sent to login with a redirect back here, then returns
 * to save. For a signed-in user the button reflects saved state (from the
 * saved-id set) and toggles it. Saving never removes the job from the list —
 * only the button's label changes.
 */
export function SaveJobButton({ jobId, className }: { jobId: number; className?: string }) {
  const navigate = useNavigate()
  const location = useLocation()
  const { data: user } = useCurrentUser()

  const savedIds = useSavedJobIds(!!user)
  const save = useSaveJob()
  const unsave = useUnsaveJob()

  const isSaved = savedIds.data?.job_ids.includes(jobId) ?? false
  const busy = save.isPending || unsave.isPending

  const onClick = () => {
    if (!user) {
      const redirect = encodeURIComponent(location.pathname + location.search)
      navigate(`/login?redirect=${redirect}`)
      return
    }
    if (isSaved) unsave.mutate(jobId)
    else save.mutate(jobId)
  }

  return (
    <button
      type="button"
      className={`btn ${isSaved ? 'btn--saved' : 'btn--outline'} ${className ?? ''}`.trim()}
      onClick={onClick}
      disabled={busy}
      aria-pressed={isSaved}
    >
      {isSaved ? '★ Saved' : '☆ Save'}
    </button>
  )
}
