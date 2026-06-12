import { useState } from 'react'
import { api } from './api'
import { Button } from './primitives'

const VERDICT_TONE = {
  ELIGIBLE: 'text-green-700',
  NOT_ELIGIBLE: 'text-red-700',
  UNVERIFIABLE: 'text-amber-700',
}

export function FomTab() {
  const [q, setQ] = useState('Can we serve a member at 301 W 2nd Street, Austin, TX?')
  const [busy, setBusy] = useState(false)
  const [answer, setAnswer] = useState(null)

  const run = async () => {
    setBusy(true)
    setAnswer(null)
    try {
      setAnswer(await api.fom(q))
    } catch (e) {
      setAnswer({ error: String(e) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-2xl px-6 py-8">
      <h2 className="text-[17px] font-semibold">Field-of-Membership Check</h2>
      <p className="mt-1 text-[13px] text-ink-2">
        Geocode → real-place check → district check, with the evidence chain compliance needs.
      </p>
      <div className="mt-4 flex gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && run()}
          className="h-9 flex-1 rounded-md border border-hairline bg-white px-3 text-[13px] outline-none focus:ring-2 focus:ring-blue-600"
        />
        <Button variant="primary" onClick={run} disabled={busy}>
          {busy ? 'Verifying…' : 'Verify'}
        </Button>
      </div>
      {answer && (
        <div className="mt-5 rounded-md border border-hairline bg-white px-4 py-3">
          {answer.error && <div className="text-[13px] text-red-700">{answer.error}</div>}
          {answer.tool_result?.status && (
            <div
              className={`text-[14px] font-semibold ${VERDICT_TONE[answer.tool_result.status] || ''}`}
            >
              {answer.tool_result.status.replace('_', ' ')}
            </div>
          )}
          {answer.answer && (
            <p className="mt-1 text-[13px] leading-relaxed text-ink-2">
              {answer.answer.replaceAll('**', '')}
            </p>
          )}
          {answer.tool_result?.evidence && (
            <div className="mt-4">
              <div className="mb-2 text-[10px] font-semibold tracking-wide text-ink-3 uppercase">
                Evidence chain
              </div>
              <div className="border-l-2 border-hairline pl-4">
                {answer.tool_result.evidence.map((step, i) => (
                  <div key={i} className="relative pb-3 text-[12.5px] last:pb-0">
                    <span className="absolute top-1 -left-[21px] h-2 w-2 rounded-full bg-blue-600" />
                    <span className="font-medium text-ink">{step.step}</span>
                    <span className="ml-1.5 rounded bg-stone-100 px-1 py-px font-mono text-[10px] text-ink-2">
                      {step.source}
                    </span>{' '}
                    <span className="text-ink-2">{step.detail}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
