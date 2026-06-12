import { useEffect, useState } from 'react'
import { api } from './api'
import { Skeleton } from './primitives'

export function AuditTab() {
  const [data, setData] = useState(null)

  useEffect(() => {
    api.audit().then(setData).catch(() => setData({ backend: '?', rows: [] }))
    const t = setInterval(() => api.audit().then(setData).catch(() => {}), 5000)
    return () => clearInterval(t)
  }, [])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center justify-between border-b border-hairline px-4 py-2.5">
        <h2 className="text-[15px] font-semibold">Audit Trail</h2>
        {data && (
          <span className="rounded bg-stone-100 px-1.5 py-0.5 font-mono text-[10px] uppercase text-ink-2">
            {data.backend}
          </span>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <table className="w-full border-collapse text-[13px]">
          <thead className="sticky top-0 bg-white">
            <tr className="border-b border-hairline">
              {['Time', 'Action', 'Source', 'Decision', 'Autonomy', 'Reason'].map((h) => (
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
            {!data &&
              [...Array(6)].map((_, i) => (
                <tr key={i} className="border-b border-hairline">
                  {[...Array(6)].map((_, j) => (
                    <td key={j} className="px-3 py-3">
                      <Skeleton className="h-3 w-full max-w-28" />
                    </td>
                  ))}
                </tr>
              ))}
            {data?.rows?.map((r, i) => (
              <tr key={i} className="border-b border-hairline align-top">
                <td className="tnum px-3 py-2 whitespace-nowrap text-ink-3">
                  {(r.ts || '').replace('T', ' ').slice(5, 19)}
                </td>
                <td className="px-3 py-2 font-medium whitespace-nowrap">{r.action}</td>
                <td className="px-3 py-2 whitespace-nowrap text-ink-2">{r.source}</td>
                <td className="px-3 py-2 whitespace-nowrap text-ink-2">{r.decision}</td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <span
                    className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${
                      r.autonomy_level === 'autonomous'
                        ? 'bg-stone-100 text-ink-2'
                        : 'bg-amber-50 text-amber-700'
                    }`}
                  >
                    {r.autonomy_level}
                  </span>
                </td>
                <td className="px-3 py-2 text-ink-2">{r.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
