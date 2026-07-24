// Small line icons for the marketing surface. Stroke icons on
// `currentColor` so they inherit the charcoal/beige context they sit in.
import type { ReactElement, SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement> & { size?: number }

export type IconComponent = (props: IconProps) => ReactElement

function base({ size = 20, ...props }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.7,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    ...props,
  }
}

/** Ascending bars — the Xcelsior mark and the market-analytics motif. */
export function BrandMark({ size = 26, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <rect x="3" y="13" width="4" height="8" rx="1.3" fill="currentColor" />
      <rect x="10" y="8" width="4" height="13" rx="1.3" fill="currentColor" />
      <rect x="17" y="3" width="4" height="18" rx="1.3" fill="currentColor" opacity="0.55" />
    </svg>
  )
}

export function BarChart(props: IconProps) {
  return (
    <svg {...base(props)} aria-hidden="true">
      <line x1="6" y1="20" x2="6" y2="13" />
      <line x1="12" y1="20" x2="12" y2="8" />
      <line x1="18" y1="20" x2="18" y2="4" />
    </svg>
  )
}

export function Briefcase(props: IconProps) {
  return (
    <svg {...base(props)} aria-hidden="true">
      <rect x="3" y="7" width="18" height="13" rx="2" />
      <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      <line x1="3" y1="12" x2="21" y2="12" />
    </svg>
  )
}

export function Clock(props: IconProps) {
  return (
    <svg {...base(props)} aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  )
}

export function ArrowRight(props: IconProps) {
  return (
    <svg {...base(props)} aria-hidden="true">
      <line x1="5" y1="12" x2="19" y2="12" />
      <path d="m13 6 6 6-6 6" />
    </svg>
  )
}

export function TrendUp(props: IconProps) {
  return (
    <svg {...base(props)} aria-hidden="true">
      <path d="M3 17 9 11l4 4 8-8" />
      <path d="M15 4h6v6" />
    </svg>
  )
}

export function Target(props: IconProps) {
  return (
    <svg {...base(props)} aria-hidden="true">
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="3.4" />
    </svg>
  )
}

export function Bolt(props: IconProps) {
  return (
    <svg {...base(props)} aria-hidden="true">
      <path d="M13 2 4 14h7l-1 8 9-12h-7z" />
    </svg>
  )
}

export function Shield(props: IconProps) {
  return (
    <svg {...base(props)} aria-hidden="true">
      <path d="M12 3 5 6v5c0 4.4 3 7.7 7 9 4-1.3 7-4.6 7-9V6z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  )
}

export function Database(props: IconProps) {
  return (
    <svg {...base(props)} aria-hidden="true">
      <ellipse cx="12" cy="5.5" rx="7" ry="2.8" />
      <path d="M5 5.5v13c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8v-13" />
      <path d="M5 12c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8" />
    </svg>
  )
}

export function DocSearch(props: IconProps) {
  return (
    <svg {...base(props)} aria-hidden="true">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h6" />
      <path d="M14 3v4a1 1 0 0 0 1 1h4" />
      <circle cx="16" cy="15" r="3" />
      <line x1="18.2" y1="17.2" x2="21" y2="20" />
    </svg>
  )
}

export function Lightbulb(props: IconProps) {
  return (
    <svg {...base(props)} aria-hidden="true">
      <path d="M9 18h6" />
      <path d="M10 21h4" />
      <path d="M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.4 1 2.5h6c0-1.1.3-1.8 1-2.5A6 6 0 0 0 12 3Z" />
    </svg>
  )
}

export function Search(props: IconProps) {
  return (
    <svg {...base(props)} aria-hidden="true">
      <circle cx="11" cy="11" r="7" />
      <line x1="16.5" y1="16.5" x2="21" y2="21" />
    </svg>
  )
}

export function MapPin(props: IconProps) {
  return (
    <svg {...base(props)} aria-hidden="true">
      <path d="M20 10c0 5-8 11-8 11s-8-6-8-11a8 8 0 0 1 16 0Z" />
      <circle cx="12" cy="10" r="2.6" />
    </svg>
  )
}

export function DollarSign(props: IconProps) {
  return (
    <svg {...base(props)} aria-hidden="true">
      <line x1="12" y1="2.5" x2="12" y2="21.5" />
      <path d="M16.5 6.5H9.8a2.8 2.8 0 0 0 0 5.6h4.4a2.8 2.8 0 0 1 0 5.6H7" />
    </svg>
  )
}

export function ClipboardList(props: IconProps) {
  return (
    <svg {...base(props)} aria-hidden="true">
      <rect x="5" y="4" width="14" height="17" rx="2" />
      <path d="M9 4a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 4v1H9z" />
      <line x1="9" y1="10" x2="15" y2="10" />
      <line x1="9" y1="14" x2="15" y2="14" />
      <line x1="9" y1="17.5" x2="12.5" y2="17.5" />
    </svg>
  )
}

export function Menu(props: IconProps) {
  return (
    <svg {...base(props)} aria-hidden="true">
      <line x1="4" y1="7" x2="20" y2="7" />
      <line x1="4" y1="12" x2="20" y2="12" />
      <line x1="4" y1="17" x2="20" y2="17" />
    </svg>
  )
}

export function Close(props: IconProps) {
  return (
    <svg {...base(props)} aria-hidden="true">
      <line x1="6" y1="6" x2="18" y2="18" />
      <line x1="18" y1="6" x2="6" y2="18" />
    </svg>
  )
}
