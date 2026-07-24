import { useState } from 'react'
import { Link } from 'react-router-dom'

import { skillUrl } from '../../shared/filters'
import type { JobTechnology } from './api'

/**
 * A technology tag with its extraction evidence one hover/tap away.
 * Showing the exact sentence the extractor matched is the traceability
 * promise made visible: no statistic without a source. The name links
 * to the skill's market page.
 */
export function SkillChip({ tech }: { tech: JobTechnology }) {
  const [open, setOpen] = useState(false)

  return (
    <span
      className={`skill-chip skill-chip--${tech.requirement_level}`}
      tabIndex={0}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <Link to={skillUrl(tech.slug)} className="skill-chip__link">
        {tech.name}
      </Link>
      {open && (
        <span role="tooltip" className="skill-chip__evidence">
          <em>“{tech.evidence_snippet}”</em>
          <small>
            {tech.category.replace('_', '/')} · confidence {Math.round(tech.confidence * 100)}%
          </small>
        </span>
      )}
    </span>
  )
}
