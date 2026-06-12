import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, relAge, sourceOf, SOURCE_LABELS } from './api'
import { QueueTable } from './QueueTable'
import { Workspace, prefetchWorkspace } from './workspace'
import { FomTab } from './FomTab'
import { AuditTab } from './AuditTab'

const NAV = [
  { key: 'cases', label: 'Cases' },
  { key: 'fom', label: 'FOM Verification' },
  { key: 'audit', label: 'Audit Trail' },
]
const RAIL_SOURCES = ['federal_register', 'ncua', 'nacha', 'irs']

export default function App() {
  const [tab, setTab] = useState('cases')
  const [cases, setCases] = useState(null)
  const [status, setStatus] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [cursorId, setCursorId] = useState(null)
  const [sourceFilter, setSourceFilter] = useState(null)
  const [expanded, setExpanded] = useState(false)
  const [, tick] = useState(0) // re-render for relative ages / "last poll Xs"
  const knownIds = useRef(null)
  const [newIds, setNewIds] = useState(new Set())

  const refresh = useCallback(async () => {
    try {
      const list = await api.cases()
      if (knownIds.current !== null) {
        const fresh = list.filter((c) => !knownIds.current.has(c.id)).map((c) => c.id)
        if (fresh.length) {
          setNewIds(new Set(fresh))
          setTimeout(() => setNewIds(new Set()), 2500)
        }
      }
      knownIds.current = new Set(list.map((c) => c.id))
      setCases(list)
      // warm the C1 workspace cache so case clicks render instantly
      list.forEach(prefetchWorkspace)
    } catch {
      /* poller may be mid-restart; keep last state */
    }
  }, [])

  useEffect(() => {
    refresh()
    api.status().then(setStatus).catch(() => {})
    const t1 = setInterval(refresh, 2000)
    const t2 = setInterval(() => api.status().then(setStatus).catch(() => {}), 3000)
    const t3 = setInterval(() => tick((n) => n + 1), 1000)
    return () => [t1, t2, t3].forEach(clearInterval)
  }, [refresh])

  const visible = useMemo(
    () => (cases || []).filter((c) => !sourceFilter || sourceOf(c) === sourceFilter),
    [cases, sourceFilter],
  )
  const selected = (cases || []).find((c) => c.id === selectedId) || null

  // optimistic actions: mutate local state instantly, reconcile with response
  const mutate = (id, fn) =>
    setCases((cs) => cs.map((c) => (c.id === id ? fn(structuredClone(c)) : c)))
  const nowIso = () => new Date().toISOString()
  const actions = useMemo(
    () => ({
      approve: () => {
        const id = selectedId
        mutate(id, (c) => {
          c.status = 'NOTIFIED'
          c.timeline.push({ ts: nowIso(), actor: 'human', action: 'notified', note: 'Approve & Notify' })
          return c
        })
        api.approve(id).then(refresh).catch(refresh)
      },
      update: (note) => {
        const id = selectedId
        mutate(id, (c) => {
          if (c.status === 'NOTIFIED') c.status = 'IN_PROGRESS'
          c.timeline.push({ ts: nowIso(), actor: 'human', action: 'update', note })
          return c
        })
        api.update(id, note).then(refresh).catch(refresh)
      },
      close: (note = '') => {
        const id = selectedId
        mutate(id, (c) => {
          c.status = 'CLOSED'
          c.timeline.push({ ts: nowIso(), actor: 'human', action: 'closed', note: note || 'closed by compliance officer' })
          return c
        })
        api.close(id, note).then(refresh).catch(refresh)
      },
    }),
    [selectedId, refresh],
  )

  // keyboard: ↑/↓ moves cursor, Enter opens, Esc closes panel
  useEffect(() => {
    const onKey = (e) => {
      if (tab !== 'cases' || ['INPUT', 'TEXTAREA'].includes(e.target.tagName)) return
      if (document.getElementById('canary-modal')) return // modal owns the keyboard
      if (e.key === 'Escape') setSelectedId(null)
      if (!['ArrowDown', 'ArrowUp', 'Enter'].includes(e.key)) return
      e.preventDefault()
      const ids = visible.map((c) => c.id)
      if (!ids.length) return
      if (e.key === 'Enter') {
        if (cursorId != null) setSelectedId(cursorId)
        return
      }
      const i = ids.indexOf(cursorId ?? selectedId)
      const next =
        e.key === 'ArrowDown'
          ? ids[Math.min(ids.length - 1, i + 1)]
          : ids[Math.max(0, i <= 0 ? 0 : i - 1)]
      setCursorId(next)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [tab, visible, cursorId, selectedId])

  const openCount = status?.open_cases ?? (cases || []).filter((c) => c.status !== 'CLOSED').length
  const pollAge = status?.poll?.ts ? relAge(status.poll.ts) : '—'

  return (
    <div className="flex h-screen flex-col">
      {/* top bar */}
      <header className="flex h-14 shrink-0 items-center gap-6 border-b border-hairline bg-white px-4">
        <div className="flex items-center gap-2">
          <img src="/logo.png" alt="" className="h-7 w-auto" />
          <span className="text-[15px] font-semibold tracking-tight">Canary</span>
        </div>
        <div className="flex items-center gap-2 text-[12px] text-ink-2">
          <span className="breathe h-1.5 w-1.5 rounded-full bg-green-600" />
          <span>
            Monitoring 4 sources · last poll <span className="tnum">{pollAge}</span> ago ·{' '}
            <span className="tnum font-medium">{openCount}</span> open case{openCount === 1 ? '' : 's'}
          </span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-blue-600 text-[11px] font-semibold text-white">
            SE
          </span>
          <span className="text-[12px] text-ink-2">Saad E. · Compliance</span>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* left rail */}
        <nav className="flex w-[220px] shrink-0 flex-col border-r border-hairline bg-rail px-3 py-4">
          <div className="space-y-0.5">
            {NAV.map((n) => (
              <button
                key={n.key}
                onClick={() => {
                  setTab(n.key)
                  setExpanded(false) // nav always returns you to the queue view
                }}
                className={`block w-full cursor-pointer rounded-md px-2.5 py-1.5 text-left text-[13px] font-medium transition-colors duration-150 ${
                  tab === n.key ? 'bg-blue-50 text-blue-700' : 'text-ink-2 hover:bg-stone-100'
                }`}
              >
                {n.label}
              </button>
            ))}
          </div>
          <div className="mt-6 px-2.5 text-[10px] font-semibold tracking-wide text-ink-3 uppercase">
            Sources
          </div>
          <div className="mt-1 space-y-0.5">
            {RAIL_SOURCES.map((s) => {
              const st = status?.poll?.sources?.[s]
              const active = sourceFilter === s
              return (
                <button
                  key={s}
                  onClick={() => {
                    setSourceFilter(active ? null : s)
                    setTab('cases')
                  }}
                  className={`flex w-full cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[13px] transition-colors duration-150 ${
                    active ? 'bg-blue-50 text-blue-700' : 'text-ink-2 hover:bg-stone-100'
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      st ? (st.ok ? 'bg-green-600' : 'bg-red-600') : 'bg-stone-300'
                    }`}
                  />
                  {SOURCE_LABELS[s]}
                </button>
              )
            })}
          </div>
          <div className="mt-auto px-2.5 text-[10px] text-ink-3">canary v0.6 · demo</div>
        </nav>

        {/* center pane (hidden while the workspace is expanded) */}
        <main
          className={`min-h-0 min-w-0 flex-1 flex-col bg-white ${
            tab === 'cases' && selected && expanded ? 'hidden' : 'flex'
          }`}
        >
          {tab === 'cases' && (
            <>
              <div className="flex items-center justify-between border-b border-hairline px-4 py-2.5">
                <h1 className="text-[15px] font-semibold">
                  Case Queue
                  {sourceFilter && (
                    <span className="ml-2 text-[12px] font-normal text-ink-3">
                      filtered: {SOURCE_LABELS[sourceFilter]}
                    </span>
                  )}
                </h1>
                <span className="tnum text-[12px] text-ink-3">
                  {visible.length} case{visible.length === 1 ? '' : 's'} ·{' '}
                  {visible.filter((c) => c.status !== 'CLOSED').length} open
                </span>
              </div>
              <QueueTable
                cases={visible}
                loading={cases === null}
                selectedId={selectedId}
                cursorId={cursorId}
                onSelect={(id) => {
                  setSelectedId(id)
                  setCursorId(id)
                }}
                newIds={newIds}
                compact={!!selected}
              />
            </>
          )}
          {tab === 'fom' && <FomTab />}
          {tab === 'audit' && <AuditTab />}
        </main>

        {/* right context panel — expandable to the full content area */}
        {tab === 'cases' && selected && (
          <aside
            className={`relative flex min-h-0 flex-col border-l border-hairline bg-white ${
              expanded ? 'min-w-0 flex-1' : 'w-[460px] shrink-0'
            }`}
          >
            {!expanded && (
              <button
                onClick={() => setExpanded(true)}
                title="Expand to full width"
                className="absolute top-1/2 -left-3 z-20 flex h-6 w-6 -translate-y-1/2 cursor-pointer
                           items-center justify-center rounded-full border border-hairline bg-white
                           text-[11px] text-ink-3 shadow-sm hover:text-ink"
              >
                ‹
              </button>
            )}
            <Workspace
              liveCase={selected}
              actions={actions}
              onClose={() => {
                setSelectedId(null)
                setExpanded(false)
              }}
              expanded={expanded}
              onToggleExpand={() => setExpanded((v) => !v)}
            />
          </aside>
        )}
      </div>
    </div>
  )
}
