import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { listAudit, listSpikes } from '../api/client'
import {
  DEMO_COORDINATED_SPIKE,
  DEMO_FESTIVE_SPIKE,
  SEED_42_LABEL,
  SYNTHETIC_SCENARIO,
} from '../api/constants'
import {
  errorMessage,
  formatNumber,
  formatPercent,
  formatRatio,
  formatTimestamp,
  isCoordinatedType,
  isFestiveType,
  skuSummary,
} from '../api/format'
import { auditEventLabel, friendlyCaseLabel } from '../api/presentation'
import type { AuditEvent, Spike } from '../api/types'
import { EmptyState, ErrorState, LoadingState } from '../components/states'
import { StatusBadge, severityTone } from '../components/StatusBadge'

type Filter = 'all' | 'coordinated' | 'festive' | 'high'

function matches(spike: Spike, filter: Filter): boolean {
  if (filter === 'coordinated') return isCoordinatedType(spike.spike_type)
  if (filter === 'festive') return isFestiveType(spike.spike_type)
  if (filter === 'high') return spike.severity.toLowerCase() === 'high'
  return true
}

function statusFor(events: AuditEvent[], spikeId: string): string {
  const related = events.filter((event) => event.spike_id === spikeId)
  if (related.length === 0) return 'Unreviewed'
  return auditEventLabel(related[related.length - 1].event_type)
}

export function InvestigationsPage() {
  const [spikes, setSpikes] = useState<Spike[] | null>(null)
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<Filter>('all')

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([listSpikes(controller.signal), listAudit({}, controller.signal)])
      .then(([list, audit]) => {
        setSpikes(list.spikes)
        setEvents(audit.events)
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setError(errorMessage(err))
      })
    return () => controller.abort()
  }, [])

  const visible = useMemo(
    () => (spikes ?? []).filter((spike) => matches(spike, filter)),
    [spikes, filter],
  )

  if (error) return <ErrorState title="Investigations unavailable" message={error} />
  if (!spikes) return <LoadingState label="Loading spike list from the API…" />

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="font-mono text-[11px] tracking-[0.2em] text-brass uppercase">
            {SYNTHETIC_SCENARIO}
          </p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">Investigations</h1>
          <p className="mt-2 text-sm font-semibold tracking-wide uppercase">
            Synthetic investigation queue
          </p>
          <p className="mt-1 max-w-2xl text-sm text-mute">
            Displayed spikes come from the reproducible seed-42 detector artifacts (
            {SEED_42_LABEL}), not live merchant traffic.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-sm">
          <Link className="inline-flex min-h-11 items-center rounded-md border border-danger/20 bg-[#FEF2F2] px-3 py-2 text-danger" to={`/investigations/${DEMO_COORDINATED_SPIKE}`}>
            Open coordinated demo
          </Link>
          <Link className="inline-flex min-h-11 items-center rounded-md border border-success/20 bg-[#ECFDF3] px-3 py-2 text-success" to={`/investigations/${DEMO_FESTIVE_SPIKE}`}>
            Open festive demo
          </Link>
        </div>
      </header>

      <div role="group" aria-label="Spike filters" className="flex flex-wrap gap-2">
        {(
          [
            ['all', 'All'],
            ['coordinated', 'Coordinated'],
            ['festive', 'Festive'],
            ['high', 'High severity'],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            aria-pressed={filter === value}
            onClick={() => setFilter(value)}
            className={
              filter === value
                ? 'min-h-11 rounded-md border border-brass bg-raised px-3 py-2 text-sm font-medium text-brass'
                : 'min-h-11 rounded-md border border-line bg-panel px-3 py-2 text-sm text-mute hover:text-navy'
            }
          >
            {label}
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <EmptyState title="No matching spikes" message="Try another filter." />
      ) : (
        <div className="table-wrap border border-line">
          <table className="w-full text-left text-sm">
            <thead className="bg-raised text-[11px] tracking-[0.12em] text-mute uppercase">
              <tr>
                <th className="px-3 py-2 font-medium">Severity</th>
                <th className="px-3 py-2 font-medium">Type</th>
                <th className="px-3 py-2 font-medium">Timestamp</th>
                <th className="px-3 py-2 font-medium">Volume Δ</th>
                <th className="px-3 py-2 font-medium">Failure</th>
                <th className="px-3 py-2 font-medium">Coordination</th>
                <th className="px-3 py-2 font-medium">Accounts</th>
                <th className="px-3 py-2 font-medium">Devices</th>
                <th className="px-3 py-2 font-medium">SKUs</th>
                <th className="px-3 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((spike) => (
                <tr key={spike.spike_id} className="border-t border-line">
                  <td className="px-3 py-2">
                    <Link className="block" to={`/investigations/${spike.spike_id}`}>
                      <StatusBadge label={spike.severity} tone={severityTone(spike.severity)} />
                      <span className="mt-1 block text-[11px] text-brass">
                        {friendlyCaseLabel(spike.spike_id, 'Case')}
                      </span>
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-mute">{spike.spike_type.replaceAll('_', ' ')}</td>
                  <td className="px-3 py-2 text-mute">{formatTimestamp(spike.window_start)}</td>
                  <td className="px-3 py-2">{formatRatio(spike.volume_change_ratio)}</td>
                  <td className="px-3 py-2">{formatPercent(spike.failure_rate)}</td>
                  <td className="px-3 py-2">{spike.coordination_score.toFixed(2)}</td>
                  <td className="px-3 py-2">{formatNumber(spike.unique_accounts)}</td>
                  <td className="px-3 py-2">{formatNumber(spike.unique_devices)}</td>
                  <td className="px-3 py-2 font-mono text-xs">{skuSummary(spike.top_skus)}</td>
                  <td className="px-3 py-2 text-mute">{statusFor(events, spike.spike_id)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
