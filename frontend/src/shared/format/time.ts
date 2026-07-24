// Human-friendly "time since" for freshness labels (e.g. the homepage's
// "Updated 2 days ago"). The input is the API's computed_at timestamp, so
// the label always reflects real data, never a mockup constant.

const MINUTE = 60
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

export function relativeTimeSince(iso: string, now: Date = new Date()): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const seconds = Math.max(0, Math.floor((now.getTime() - then) / 1000))

  if (seconds < MINUTE) return 'just now'
  if (seconds < HOUR) return plural(Math.floor(seconds / MINUTE), 'minute')
  if (seconds < DAY) return plural(Math.floor(seconds / HOUR), 'hour')
  if (seconds < 30 * DAY) return plural(Math.floor(seconds / DAY), 'day')
  return plural(Math.floor(seconds / (30 * DAY)), 'month')
}

function plural(n: number, unit: string): string {
  return `${n} ${unit}${n === 1 ? '' : 's'} ago`
}
