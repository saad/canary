import { useEffect, useRef } from 'react'
import { relAge, sourceOf } from './api'
import { ImpactCell, SourceBadge, StatusPill, UnitChips, Skeleton } from './primitives'

export function QueueTable({ cases, loading, selectedId, cursorId, onSelect, newIds, compact }) {
  // panel-open state: title keeps priority — source column hides, chips cap at 1
  const headers = compact
    ? ['Impact', 'Title', 'Owners', 'Status', 'Age']
    : ['Impact', 'Source', 'Title', 'Owners', 'Status', 'Age']
  const ref = useRef(null)

  useEffect(() => {
    // keep the keyboard cursor visible
    if (cursorId == null) return
    ref.current
      ?.querySelector(`[data-case="${cursorId}"]`)
      ?.scrollIntoView({ block: 'nearest' })
  }, [cursorId])

  return (
    <div ref={ref} className="min-h-0 flex-1 overflow-y-auto">
      <table className="w-full border-collapse text-[13px]">
        <thead className="sticky top-0 z-10 bg-white">
          <tr className="border-b border-hairline">
            {headers.map((h) => (
              <th
                key={h}
                className="px-3 py-2 text-left text-[11px] font-semibold tracking-wide text-ink-3 uppercase"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading &&
            [...Array(4)].map((_, i) => (
              <tr key={i} className="border-b border-hairline">
                {headers.map((h) => (
                  <td key={h} className="px-3 py-3.5">
                    <Skeleton className="h-3 w-full max-w-32" />
                  </td>
                ))}
              </tr>
            ))}
          {!loading && cases.length === 0 && (
            <tr>
              <td colSpan={headers.length} className="px-3 py-12 text-center text-ink-3">
                No cases yet — the canary is watching.
              </td>
            </tr>
          )}
          {cases.map((c) => {
            const isSel = c.id === selectedId
            const isCur = c.id === cursorId
            const isNew = newIds.has(c.id)
            return (
              <tr
                key={c.id}
                data-case={c.id}
                onClick={() => onSelect(c.id)}
                className={`h-11 cursor-pointer border-b border-hairline transition-colors duration-150
                  ${isNew ? 'row-in' : ''}
                  ${isSel ? 'bg-blue-50 shadow-[inset_2px_0_0_0_var(--color-blue-600)]' : 'hover:bg-stone-50'}
                  ${isCur && !isSel ? 'bg-stone-50' : ''}`}
              >
                <td className="px-3 whitespace-nowrap">
                  <ImpactCell level={c.impact_level} pulse={isNew && c.impact_level === 'HIGH'} />
                </td>
                {!compact && (
                  <td className="px-3">
                    <SourceBadge source={sourceOf(c)} />
                  </td>
                )}
                <td className="max-w-0 w-full truncate px-3 font-medium" title={c.title}>
                  {c.title || c.item_id}
                </td>
                <td className="px-3 whitespace-nowrap">
                  <UnitChips units={c.owner_units || []} max={compact ? 1 : 3} />
                </td>
                <td className="px-3 whitespace-nowrap">
                  <StatusPill status={c.status} impact={c.impact_level} escalated />
                </td>
                <td className="tnum px-3 whitespace-nowrap text-ink-3">{relAge(c.opened_ts)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
