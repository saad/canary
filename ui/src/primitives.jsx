import { SOURCE_LABELS } from './api'

// shadcn-style primitives, hand-rolled to the Canary token set.
// Semantic color is reserved for impact/status; blue-600 is the one accent.

export const IMPACT = {
  HIGH: { dot: 'bg-red-700', pill: 'bg-red-50 text-red-700' },
  MED: { dot: 'bg-amber-700', pill: 'bg-amber-50 text-amber-700' },
  LOW: { dot: 'bg-green-700', pill: 'bg-green-50 text-green-700' },
}

export function statusTone(status, impact) {
  if (status === 'CLOSED') return 'bg-green-50 text-green-700'
  if (status === 'IN_PROGRESS') return 'bg-amber-50 text-amber-700'
  if (status === 'TRIAGED' && impact === 'HIGH') return 'bg-red-50 text-red-700'
  if (status === 'TRIAGED') return 'bg-amber-50 text-amber-700'
  return 'bg-stone-100 text-stone-600' // NEW, NOTIFIED
}

export const STATUS_LABEL = {
  NEW: 'New',
  TRIAGED: 'Triaged',
  NOTIFIED: 'Notified',
  IN_PROGRESS: 'In progress',
  CLOSED: 'Closed',
}

export function StatusPill({ status, impact, escalated }) {
  const label =
    status === 'TRIAGED' && impact === 'HIGH' && escalated
      ? 'Awaiting review'
      : STATUS_LABEL[status] || status
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold
                  whitespace-nowrap transition-colors duration-200 ${statusTone(status, impact)}`}
    >
      {label}
    </span>
  )
}

export function ImpactCell({ level, pulse }) {
  const tone = IMPACT[level] || { dot: 'bg-stone-300', pill: 'bg-stone-100 text-stone-500' }
  return (
    <span className="inline-flex items-center gap-2">
      <span className={`h-2 w-2 rounded-full ${tone.dot} ${pulse ? 'dot-pulse-once' : ''}`} />
      <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${tone.pill}`}>
        {level || '—'}
      </span>
    </span>
  )
}

export function SourceBadge({ source }) {
  return (
    <span className="inline-flex rounded border border-hairline px-1.5 py-0.5 font-mono text-[10px] font-medium uppercase tracking-wide text-ink-2">
      {SOURCE_LABELS[source] || source}
    </span>
  )
}

export function UnitChips({ units, max = 3 }) {
  const shown = units.slice(0, max)
  const extra = units.length - shown.length
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap">
      {shown.map((u) => (
        <span key={u} className="rounded bg-stone-100 px-1.5 py-0.5 text-[11px] whitespace-nowrap text-ink-2">
          {u}
        </span>
      ))}
      {extra > 0 && <span className="text-[11px] text-ink-3">+{extra}</span>}
    </span>
  )
}

export function Button({ variant = 'secondary', className = '', ...props }) {
  const styles = {
    primary: 'bg-blue-600 text-white hover:bg-blue-700',
    secondary: 'border border-hairline bg-white text-ink hover:bg-stone-50',
    ghost: 'text-ink-2 hover:bg-stone-100',
  }
  return (
    <button
      className={`inline-flex h-8 cursor-pointer items-center justify-center gap-1.5 rounded-md px-3
                  text-[13px] font-medium outline-none transition-colors duration-150
                  disabled:cursor-default disabled:opacity-50 ${styles[variant]} ${className}`}
      {...props}
    />
  )
}

export function Skeleton({ className = '' }) {
  return <div className={`animate-pulse rounded bg-stone-200/70 ${className}`} />
}
