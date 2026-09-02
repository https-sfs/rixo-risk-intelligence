import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { listAudit, listSpikes } from '../api/client'
import {
  DEMO_COORDINATED_SPIKE,
  DEMO_FESTIVE_SPIKE,
  HUMAN_APPROVAL_REQUIRED,
  SEED_42_LABEL,
  SIMULATION_ONLY,
  SYNTHETIC_SCENARIO,
} from '../api/constants'
import {
  errorMessage,
  formatNumber,
  formatPercent,
  formatTimestamp,
  isCoordinatedType,
  isFestiveType,
} from '../api/format'
import { auditEventLabel, friendlyCaseLabel } from '../api/presentation'
import type { AuditEvent, Spike, SpikeList } from '../api/types'
import { EmptyState, ErrorState, LoadingState } from '../components/states'
import { StatusBadge, severityTone } from '../components/StatusBadge'

function latestStatus(events: AuditEvent[], spikeId: string): string {
  const related = events.filter((event) => event.spike_id === spikeId)
  if (related.length === 0) return 'Ready to investigate'
  const last = related[related.length - 1]
  return auditEventLabel(last.event_type)
}

function detectorLabel(spikeType: string): string {
  return spikeType.replaceAll('_', ' ').toUpperCase()
}

export function OverviewPage() {
  const [spikes, setSpikes] = useState<Spike[] | null>(null)
  const [heldout, setHeldout] = useState<SpikeList['heldout_detection']>(null)
  const [heldoutInvestigation, setHeldoutInvestigation] = useState<SpikeList['heldout_investigation']>(null)
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([listSpikes(controller.signal), listAudit({}, controller.signal)])
      .then(([spikeList, audit]) => {
        setSpikes(spikeList.spikes)
        setHeldout(spikeList.heldout_detection ?? null)
        setHeldoutInvestigation(spikeList.heldout_investigation ?? null)
        setEvents(audit.events)
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setError(errorMessage(err))
      })
    return () => controller.abort()
  }, [])

  const metrics = useMemo(() => {
    if (!spikes) return null
    return {
      detected: spikes.length,
      high: spikes.filter((item) => item.severity.toLowerCase() === 'high').length,
      coordinated: spikes.filter((item) => isCoordinatedType(item.spike_type)).length,
      festive: spikes.filter((item) => isFestiveType(item.spike_type)).length,
    }
  }, [spikes])

  const rows = useMemo(() => {
    if (!spikes) return []
    return [...spikes]
      .sort((a, b) => b.coordination_score - a.coordination_score)
      .slice(0, 10)
  }, [spikes])

  const festiveSpike = spikes?.find((item) => item.spike_id === DEMO_FESTIVE_SPIKE)
  const coordinatedSpike = spikes?.find((item) => item.spike_id === DEMO_COORDINATED_SPIKE)

  if (error) return <ErrorState title="Overview unavailable" message={error} />
  if (!spikes || !metrics) return <LoadingState label="Loading detected spikes from the API…" />

  return (
    <div className="space-y-8">
      <header>
        <p className="font-mono text-[11px] tracking-[0.2em] text-brass uppercase">
          {SYNTHETIC_SCENARIO}
        </p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">Overview</h1>
        <p className="mt-2 font-mono text-sm tracking-wide text-brass">Seed 42</p>
        <p className="mt-2 max-w-2xl text-sm text-mute">
          Controlled synthetic payment world used for the reproducible demo.
        </p>
        <p className="mt-2 max-w-2xl text-sm text-mute">
          Counts below are simple aggregates from <code>GET /api/spikes</code>. They are
          seed-42 detector artifacts, not live merchant traffic.
        </p>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Operational metrics">
        {[
          ['Detected spikes', metrics.detected, 'neutral'],
          ['High severity', metrics.high, 'danger'],
          ['Coordinated type', metrics.coordinated, 'danger'],
          ['Festive type', metrics.festive, 'success'],
        ].map(([label, value, tone]) => (
          <article key={String(label)} className="border border-line bg-panel px-4 py-4 shadow-[0_1px_2px_rgba(23,43,77,0.04)]">
            <p className="text-[11px] tracking-[0.14em] text-mute uppercase">{label}</p>
            <p
              className={
                tone === 'danger'
                  ? 'mt-2 text-3xl font-semibold text-danger'
                  : tone === 'success'
                    ? 'mt-2 text-3xl font-semibold text-success'
                    : 'mt-2 text-3xl font-semibold text-navy'
              }
            >
              {value}
            </p>
            <p className="mt-2 text-[11px] text-mute">Source: GET /api/spikes · {SEED_42_LABEL}</p>
          </article>
        ))}
      </section>

      {heldout ? (
        <section className="border border-line bg-panel px-4 py-4" aria-label="Held-out detection">
          <h2 className="text-lg font-semibold">Held-out detection metrics</h2>
          <p className="mt-1 text-xs text-mute">
            {String(heldout.evaluation_status ?? 'EVALUATION')} · {String(heldout.source ?? '')}
          </p>
          <p className="mt-1 text-xs text-mute">
            Not the seed-42 demo ledger and not a production accuracy claim.
          </p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <article className="border border-line bg-raised px-3 py-3">
              <p className="text-[11px] tracking-[0.12em] text-mute uppercase">Any-scenario precision</p>
              <p className="mt-1 text-xl font-semibold">{formatPercent(Number(heldout.any_precision))}</p>
            </article>
            <article className="border border-line bg-raised px-3 py-3">
              <p className="text-[11px] tracking-[0.12em] text-mute uppercase">Any-scenario recall</p>
              <p className="mt-1 text-xl font-semibold">{formatPercent(Number(heldout.any_recall))}</p>
            </article>
            <article className="border border-line bg-raised px-3 py-3">
              <p className="text-[11px] tracking-[0.12em] text-mute uppercase">False positives</p>
              <p className="mt-1 text-xl font-semibold">{formatNumber(Number(heldout.any_fp))}</p>
            </article>
            <article className="border border-line bg-raised px-3 py-3">
              <p className="text-[11px] tracking-[0.12em] text-mute uppercase">False negatives</p>
              <p className="mt-1 text-xl font-semibold">{formatNumber(Number(heldout.any_fn))}</p>
            </article>
          </div>
          {heldoutInvestigation ? (
            <p className="mt-3 text-xs text-mute">
              Deterministic investigation accuracy {formatPercent(Number(heldoutInvestigation.accuracy))} on{' '}
              {formatNumber(Number(heldoutInvestigation.n_detected_spikes))} held-out spikes ·{' '}
              {String(heldoutInvestigation.source ?? '')}
            </p>
          ) : null}
        </section>
      ) : null}

      <section className="grid gap-3 md:grid-cols-2" aria-label="Demo scenarios">
        <Link
          to={`/investigations/${DEMO_FESTIVE_SPIKE}`}
          className="border border-success/40 bg-success/5 px-4 py-4 hover:bg-success/10"
        >
          <p className="text-[11px] tracking-[0.14em] text-success uppercase">
            LEGITIMATE FESTIVE SURGE
          </p>
          <p className="mt-1 text-sm font-semibold">{friendlyCaseLabel(DEMO_FESTIVE_SPIKE, 'Case')}</p>
          {festiveSpike ? (
            <p className="mt-1 text-xs text-mute">
              Detector type from API: {detectorLabel(festiveSpike.spike_type)}
              {' · '}Volume {formatNumber(festiveSpike.volume)}
            </p>
          ) : null}
          <dl className="mt-3 space-y-1 text-sm">
            <div>
              <dt className="inline text-mute">Detector: </dt>
              <dd className="inline font-semibold tracking-wide uppercase">
                LEGITIMATE FESTIVE SPIKE
              </dd>
            </div>
            <div>
              <dt className="inline text-mute">Investigator: </dt>
              <dd className="inline font-semibold tracking-wide uppercase">LIKELY FESTIVE</dd>
            </div>
            <div>
              <dt className="inline text-mute">Recommendation: </dt>
              <dd className="inline font-semibold tracking-wide uppercase">MONITOR</dd>
            </div>
            <div>
              <dt className="inline text-mute">Guardrail: </dt>
              <dd className="inline font-semibold tracking-wide uppercase">NO TIGHTEN_RULE</dd>
            </div>
          </dl>
        </Link>
        <Link
          to={`/investigations/${DEMO_COORDINATED_SPIKE}`}
          className="border border-danger/40 bg-danger/5 px-4 py-4 hover:bg-danger/10"
        >
          <p className="text-[11px] tracking-[0.14em] text-danger uppercase">
            COORDINATED ABUSE
          </p>
          <p className="mt-1 text-sm font-semibold">{friendlyCaseLabel(DEMO_COORDINATED_SPIKE, 'Case')}</p>
          {coordinatedSpike ? (
            <p className="mt-1 text-xs text-mute">
              Detector type from API: {detectorLabel(coordinatedSpike.spike_type)}
              {' · '}Volume {formatNumber(coordinatedSpike.volume)}
            </p>
          ) : null}
          <dl className="mt-3 space-y-1 text-sm">
            <div>
              <dt className="inline text-mute">Detector: </dt>
              <dd className="inline font-semibold tracking-wide uppercase">
                SUSPICIOUS COORDINATED SPIKE
              </dd>
            </div>
            <div>
              <dt className="inline text-mute">Investigator: </dt>
              <dd className="inline font-semibold tracking-wide uppercase">COORDINATED ABUSE</dd>
            </div>
            <div>
              <dt className="inline text-mute">Recommendation: </dt>
              <dd className="inline font-semibold tracking-wide uppercase">TIGHTEN_RULE</dd>
            </div>
            <div>
              <dt className="inline text-mute">Scope: </dt>
              <dd className="inline font-semibold tracking-wide uppercase">
                WINDOW + DEVICE + SUBNET + SKU
              </dd>
            </div>
            <div>
              <dt className="inline text-mute">Approval: </dt>
              <dd className="inline font-semibold tracking-wide uppercase">
                {HUMAN_APPROVAL_REQUIRED}
              </dd>
            </div>
            <div>
              <dt className="inline text-mute">Execution: </dt>
              <dd className="inline font-semibold tracking-wide uppercase">{SIMULATION_ONLY}</dd>
            </div>
          </dl>
        </Link>
      </section>

      <section>
        <h2 className="text-lg font-semibold">Recent / high-risk spikes</h2>
        <p className="mt-1 text-sm text-mute">
          Sorted by coordination score from the seed-42 detector artifact. Open a row to
          investigate.
        </p>
        {rows.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              title="No spikes returned"
              message="The API returned an empty spike list."
            />
          </div>
        ) : (
          <div className="table-wrap mt-4 border border-line">
            <table className="w-full text-left text-sm">
              <thead className="bg-raised text-[11px] tracking-[0.12em] text-mute uppercase">
                <tr>
                  <th className="px-3 py-2 font-medium">Spike</th>
                  <th className="px-3 py-2 font-medium">Time</th>
                  <th className="px-3 py-2 font-medium">Severity</th>
                  <th className="px-3 py-2 font-medium">Type</th>
                  <th className="px-3 py-2 font-medium">Volume</th>
                  <th className="px-3 py-2 font-medium">Failure</th>
                  <th className="px-3 py-2 font-medium">Coordination</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((spike) => (
                  <tr key={spike.spike_id} className="border-t border-line">
                    <td className="px-3 py-2 text-sm">
                      <Link
                        className="text-brass hover:underline"
                        to={`/investigations/${spike.spike_id}`}
                      >
                        {friendlyCaseLabel(spike.spike_id, 'Case')}
                      </Link>
                    </td>
                    <td className="px-3 py-2 text-mute">
                      {formatTimestamp(spike.window_start)}
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge label={spike.severity} tone={severityTone(spike.severity)} />
                    </td>
                    <td className="px-3 py-2 text-mute">{spike.spike_type.replaceAll('_', ' ')}</td>
                    <td className="px-3 py-2">{formatNumber(spike.volume)}</td>
                    <td className="px-3 py-2">{formatPercent(spike.failure_rate)}</td>
                    <td className="px-3 py-2">{spike.coordination_score.toFixed(2)}</td>
                    <td className="px-3 py-2 text-mute">{latestStatus(events, spike.spike_id)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
