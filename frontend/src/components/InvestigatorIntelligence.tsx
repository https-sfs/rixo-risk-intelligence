import { formatNumber, formatRatio } from '../api/format'
import type { InvestigationIntelligence, ProvenancedMetric } from '../api/types'

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && !Number.isNaN(value) ? value : null
}

function provenanceLabel(value: unknown): string {
  const raw = asString(value).toUpperCase()
  if (raw === 'OBSERVED') return 'Observed'
  if (raw === 'DERIVED' || raw.startsWith('DERIVED')) return 'Derived'
  if (raw === 'BASELINE') return 'Baseline'
  if (raw === 'EVALUATION') return 'Evaluation'
  if (raw.includes('SCENARIO')) return 'Scenario'
  if (raw.includes('MODEL')) return 'Model'
  if (raw.includes('PROXY')) return 'Proxy'
  return raw ? raw.replaceAll('_', ' ') : 'Unknown'
}

function metricValue(block: unknown): unknown {
  const record = asRecord(block)
  return 'value' in record ? record.value : block
}

function BriefList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null
  return (
    <div>
      <h3 className="text-[11px] tracking-[0.14em] text-mute uppercase">{title}</h3>
      <ul className="mt-2 list-disc space-y-1 pl-4 text-sm">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  )
}

function MetricChip({ item }: { item: ProvenancedMetric }) {
  const value = item.value
  const shown =
    typeof value === 'number'
      ? value > 0 && value < 1 && (item.label ?? '').toLowerCase().includes('coverage')
        ? `${(value * 100).toFixed(2)}%`
        : formatNumber(value)
      : value == null
        ? '—'
        : String(value)
  return (
    <article className="border border-line bg-raised px-3 py-3">
      <p className="text-[11px] tracking-[0.12em] text-mute uppercase">{item.label ?? 'Metric'}</p>
      <p className="mt-1 text-xl font-semibold">{shown}</p>
      <p className="mt-1 text-[11px] text-mute">
        {provenanceLabel(item.provenance)}
        {item.source ? ` · ${item.source}` : ''}
      </p>
    </article>
  )
}

function NeighborBars({
  neighbors,
}: {
  neighbors: Array<{
    label?: string
    transaction_count?: number | null
    is_selected?: boolean
  }>
}) {
  const max = Math.max(
    1,
    ...neighbors.map((row) => (typeof row.transaction_count === 'number' ? row.transaction_count : 0)),
  )
  return (
    <div className="mt-3 flex h-16 items-end gap-1" aria-label="Neighboring hours">
      {neighbors.map((row) => {
        const count = typeof row.transaction_count === 'number' ? row.transaction_count : 0
        const height = `${Math.max(8, Math.round((count / max) * 100))}%`
        return (
          <div
            key={row.label ?? String(count)}
            className={row.is_selected ? 'flex-1 bg-brass' : 'flex-1 bg-line'}
            style={{ height }}
            title={`${row.label ?? ''} · ${formatNumber(count)}`}
          />
        )
      })}
    </div>
  )
}

export function InvestigatorIntelligence({
  intelligence,
}: {
  intelligence?: InvestigationIntelligence | null
}) {
  if (!intelligence) return null
  const brief = intelligence.brief ?? {}
  const status = intelligence.classifier_status
  const temporal = intelligence.temporal
  const entities = intelligence.entities
  const baseline = intelligence.baseline
  const fp = intelligence.false_positive_impact
  const metrics = intelligence.case_metrics ?? []
  const neighbors = temporal?.neighbors ?? []
  const groups = entities?.groups ?? {}
  const currentVolume = asNumber(asRecord(baseline?.current).volume)
  const baselineVolume = asNumber(asRecord(baseline?.baseline).volume)
  const deviation = asRecord(baseline?.deviation)

  return (
    <section className="space-y-6" data-testid="investigator-intelligence">
      <section className="border border-line bg-panel p-5">
        <h2 className="text-lg font-semibold">Investigator summary</h2>
        <p className="mt-1 text-xs text-mute">
          Structured evidence for this case. Not a generated narrative.
        </p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <BriefList title="Why this case was flagged" items={brief.why_flagged ?? []} />
          <BriefList title="What supports the risk assessment" items={brief.what_supports_risk ?? []} />
          <BriefList title="What is actually observed" items={brief.observed ?? []} />
          <BriefList title="What is derived" items={brief.derived ?? []} />
          <BriefList title="What is uncertain / missing" items={brief.uncertain ?? []} />
          <BriefList title="What the investigator should check next" items={brief.next_checks ?? []} />
        </div>
      </section>

      {status ? (
        <section className="border border-line bg-panel p-5">
          <p className="font-mono text-[11px] tracking-[0.16em] text-brass uppercase">
            {status.headline ?? `MODEL EVIDENCE: ${status.status ?? 'UNAVAILABLE'}`}
          </p>
          <p className="mt-2 text-sm">{status.detail}</p>
          <p className="mt-2 text-xs text-mute">
            This status is an evidence-quality classification. It is not a fraud verdict and
            does not authorize approval or simulation. High classifier score is supporting
            risk evidence only. It is not the anomaly detector and not an autonomous action.
          </p>
        </section>
      ) : null}

      {metrics.length > 0 ? (
        <section>
          <h2 className="text-lg font-semibold">Case metrics</h2>
          <p className="mt-1 text-xs text-mute">Only values with known provenance are shown.</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {metrics.map((item) => (
              <MetricChip key={`${item.label}-${item.source}`} item={item} />
            ))}
          </div>
        </section>
      ) : null}

      {fp ? (
        <section className="border border-line bg-panel p-5">
          <h2 className="text-lg font-semibold">{fp.headline ?? 'Potential false-positive impact'}</h2>
          <p className="mt-1 text-[11px] tracking-[0.12em] text-mute uppercase">
            {provenanceLabel(fp.provenance)} · operational interpretation
          </p>
          <p className="mt-2 text-sm">{fp.note}</p>
          <ul className="mt-3 list-disc space-y-1 pl-4 text-sm">
            {(fp.impacts ?? []).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-mute">
            No financial savings figure is available. Observed facts, derived estimates, and
            scenario assumptions are labelled separately.
          </p>
        </section>
      ) : null}

      {temporal ? (
        <section className="border border-line bg-panel p-5">
          <h2 className="text-lg font-semibold">Temporal breakdown</h2>
          {temporal.available === false ? (
            <p className="mt-2 text-sm text-mute">{temporal.reason ?? 'Hourly comparison is unavailable.'}</p>
          ) : (
            <>
              <p className="mt-1 text-xs text-mute">
                {asString(temporal.baseline_note) || asString(temporal.source)}
              </p>
              <p className="mt-2 text-sm">
                Selected window {asString(asRecord(temporal.selected).label)} ·{' '}
                {formatNumber(asNumber(metricValue(asRecord(temporal.selected).transaction_count)))}{' '}
                transactions
                <span className="text-mute">
                  {' '}
                  · count {provenanceLabel(temporal.count_kind)} · intensity{' '}
                  {provenanceLabel(temporal.intensity_kind)}
                </span>
              </p>
              {neighbors.length > 0 ? <NeighborBars neighbors={neighbors} /> : null}
            </>
          )}
        </section>
      ) : null}

      {entities ? (
        <section className="border border-line bg-panel p-5">
          <h2 className="text-lg font-semibold">Entity relationships</h2>
          {entities.available ? (
            <div className="mt-3 space-y-3">
              {Object.entries(groups).map(([name, rows]) => (
                <div key={name}>
                  <p className="text-[11px] tracking-[0.12em] text-mute uppercase">{name.replaceAll('_', ' ')}</p>
                  <ul className="mt-1 space-y-1 text-sm">
                    {rows.slice(0, 3).map((row) => (
                      <li key={String(row.id)}>
                        {String(row.id ?? '—')}
                        {row.count != null ? ` · ${formatNumber(asNumber(row.count))} txs` : ''}
                        {row.share != null ? ` · share ${asNumber(row.share)?.toFixed(2) ?? row.share}` : ''}
                        {' · '}
                        {provenanceLabel(row.provenance)}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
              {entities.note ? <p className="text-xs text-mute">{entities.note}</p> : null}
            </div>
          ) : (
            <p className="mt-2 text-sm text-mute">
              {entities.note ?? 'This world does not contain identifiers that support entity clustering.'}
            </p>
          )}
          {(entities.missing ?? []).length > 0 ? (
            <p className="mt-2 text-xs text-mute">Missing: {(entities.missing ?? []).join(', ')}.</p>
          ) : null}
        </section>
      ) : null}

      {baseline ? (
        <section className="border border-line bg-panel p-5">
          <h2 className="text-lg font-semibold">Historical baseline</h2>
          {baseline.available === false ? (
            <p className="mt-2 text-sm text-mute">{baseline.reason}</p>
          ) : (
            <>
              <dl className="mt-3 grid gap-3 sm:grid-cols-3 text-sm">
                <div>
                  <dt className="text-mute">Current activity</dt>
                  <dd className="font-semibold">{formatNumber(currentVolume)}</dd>
                </div>
                <div>
                  <dt className="text-mute">Baseline activity</dt>
                  <dd className="font-semibold">{formatNumber(baselineVolume)}</dd>
                </div>
                <div>
                  <dt className="text-mute">Deviation</dt>
                  <dd className="font-semibold">
                    {asNumber(deviation.ratio) != null
                      ? formatRatio(asNumber(deviation.ratio))
                      : '—'}
                  </dd>
                </div>
              </dl>
              <p className="mt-3 text-xs text-mute">
                {provenanceLabel(baseline.provenance)} · {asString(baseline.definition)}
              </p>
            </>
          )}
        </section>
      ) : null}
    </section>
  )
}
