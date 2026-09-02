import { useEffect, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { listAudit } from '../api/client'
import { errorMessage, formatTechnicalTimestamp, formatTimestamp } from '../api/format'
import { actionTypeLabel, auditEventLabel, friendlyCaseLabel } from '../api/presentation'
import type { AuditEvent } from '../api/types'
import { EmptyState, ErrorState, LoadingState } from '../components/states'

export function AuditPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const spikeFilter = searchParams.get('spike_id') ?? ''
  const actionFilter = searchParams.get('action_id') ?? ''
  const [spikeId, setSpikeId] = useState(spikeFilter)
  const [actionId, setActionId] = useState(actionFilter)
  const [events, setEvents] = useState<AuditEvent[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    setEvents(null)
    setError(null)
    listAudit(
      {
        spike_id: spikeFilter || undefined,
        action_id: actionFilter || undefined,
      },
      controller.signal,
    )
      .then((list) => setEvents(list.events))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setError(errorMessage(err))
      })
    return () => controller.abort()
  }, [spikeFilter, actionFilter])

  function onFilter(event: FormEvent) {
    event.preventDefault()
    const next = new URLSearchParams()
    if (spikeId.trim()) next.set('spike_id', spikeId.trim())
    if (actionId.trim()) next.set('action_id', actionId.trim())
    setSearchParams(next)
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="font-mono text-[11px] tracking-[0.2em] text-brass uppercase">
          SIMULATION AUDIT TRAIL
        </p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">Audit</h1>
        <p className="mt-2 max-w-3xl text-sm text-mute">
          Human-facing simulation events only: Decision recorded, Action proposed, Approval
          recorded, Simulation completed, Simulation verified, and Razorpay test simulation
          completed or failed. Technical event codes belong under Technical audit details. This
          is not a production payment audit and does not load the transaction ledger.
        </p>
      </header>

      <form onSubmit={onFilter} className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="mb-1 block text-mute">Spike ID</span>
          <input
            value={spikeId}
            onChange={(event) => setSpikeId(event.target.value)}
            className="w-72 border border-line bg-canvas px-3 py-2 font-mono text-sm"
            name="spike_id"
          />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-mute">Action ID</span>
          <input
            value={actionId}
            onChange={(event) => setActionId(event.target.value)}
            className="w-72 border border-line bg-canvas px-3 py-2 font-mono text-sm"
            name="action_id"
          />
        </label>
        <button type="submit" className="bg-ink px-4 py-2 text-sm font-semibold text-canvas">
          Apply filters
        </button>
      </form>

      {error ? <ErrorState title="Audit unavailable" message={error} /> : null}
      {!error && events == null ? <LoadingState label="Loading audit events…" /> : null}
      {events && events.length === 0 ? (
        <EmptyState
          title="No audit events"
          message="Propose, approve, and simulate an action to write the trail."
        />
      ) : null}
      {events && events.length > 0 ? (
        <div className="table-wrap border border-line bg-panel">
          <table className="w-full text-left text-sm">
            <thead className="text-[11px] tracking-[0.12em] text-mute uppercase">
              <tr>
                <th className="px-3 py-3 font-medium">Timestamp</th>
                <th className="px-3 py-3 font-medium">Decision</th>
                <th className="px-3 py-3 font-medium">Case</th>
                <th className="px-3 py-3 font-medium">Actor</th>
                <th className="px-3 py-3 font-medium">Action</th>
                <th className="px-3 py-3 font-medium">Evidence</th>
              </tr>
            </thead>
            <tbody>
              {events.map((item) => {
                const action = typeof item.details.action_type === 'string' ? item.details.action_type : null
                return (
                  <tr key={item.event_id} className="border-t border-line align-top">
                    <td className="px-3 py-3 text-mute">{formatTimestamp(item.timestamp)}</td>
                    <td className="px-3 py-3 font-semibold text-navy">{auditEventLabel(item.event_type)}</td>
                    <td className="px-3 py-3">{friendlyCaseLabel(item.spike_id, 'Case')}</td>
                    <td className="px-3 py-3">Actor {item.actor}</td>
                    <td className="px-3 py-3 text-mute">{action ? actionTypeLabel(action) : '—'}</td>
                    <td className="px-3 py-3">
                      <details>
                        <summary className="cursor-pointer text-xs text-brass">Technical audit details</summary>
                        <div className="mt-2 space-y-1 font-mono text-xs text-mute">
                          <p>Event code: {item.event_type}</p>
                          <p>UTC timestamp: {formatTechnicalTimestamp(item.timestamp)}</p>
                          <p>Event ID: {item.event_id}</p>
                          <p>
                            Internal case ID:{' '}
                            <Link className="text-brass hover:underline" to={`/investigations/${item.spike_id}`}>
                              {item.spike_id}
                            </Link>
                          </p>
                          <p>Action ID: {item.action_id}</p>
                          {Object.keys(item.details).length > 0 ? (
                            <pre className="overflow-x-auto">{JSON.stringify(item.details, null, 2)}</pre>
                          ) : null}
                        </div>
                      </details>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  )
}
