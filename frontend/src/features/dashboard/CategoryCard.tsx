import { useState } from 'react'
import { Link } from 'react-router-dom'

import { skillUrl, type JobFilters } from '../../shared/filters'
import type { CategoryStats } from './api'

const COLLAPSED_COUNT = 5

/**
 * One taxonomy category card (Skills page). Every technology row links to
 * that skill's detail page carrying the current scope; the skill page's own
 * "view all" continues into the search behind the same predicate, so the
 * count and every click-through along the way agree. "View all" and "+N more"
 * expand the list in place — the same disclosure, offered top and bottom to
 * match the card layout.
 */
export function CategoryCard({
  category,
  filters,
  analyzed,
}: {
  category: CategoryStats
  filters: JobFilters
  analyzed: number
}) {
  const [expanded, setExpanded] = useState(false)
  const visible = expanded
    ? category.technologies
    : category.technologies.slice(0, COLLAPSED_COUNT)
  const max = category.technologies[0]?.count ?? 1
  const hasMore = category.technologies.length > COLLAPSED_COUNT

  return (
    <div className="cat-card">
      <div className="cat-card__head">
        <h3 className="cat-card__title">{category.label}</h3>
        {hasMore && (
          <button
            type="button"
            className="cat-card__viewall"
            onClick={() => setExpanded((open) => !open)}
            aria-expanded={expanded}
          >
            {expanded ? 'Show less' : 'View all →'}
          </button>
        )}
      </div>

      <ul className="cat-rows">
        {visible.map((tech) => (
          <li key={tech.slug}>
            <Link className="cat-row" to={skillUrl(tech.slug, filters)}>
              <span className="cat-row__name">{tech.name}</span>
              <span className="bar">
                <span className="bar__fill" style={{ width: `${(tech.count / max) * 100}%` }} />
              </span>
              <span className="cat-row__pct">{Math.round(tech.share * 100)}%</span>
              <span
                className="cat-row__count"
                title={`${tech.count.toLocaleString()} of ${analyzed.toLocaleString()} analyzed jobs`}
              >
                {tech.count.toLocaleString()}
              </span>
            </Link>
          </li>
        ))}
      </ul>

      {hasMore && !expanded && (
        <button
          type="button"
          className="cat-card__more"
          onClick={() => setExpanded(true)}
        >
          +{category.technologies.length - COLLAPSED_COUNT} more
        </button>
      )}
    </div>
  )
}
