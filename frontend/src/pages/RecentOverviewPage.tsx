import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getRecentBenchmark, getRecentEvaluation, listRecentAnomalies } from '../api/client'
import { RECENT_DATASET_NAME, RECENT_PUBLIC_DATA, ZENODO_RECENT_URL } from '../api/constants'
import { errorMessage, formatNumber, formatPercent, formatTimestamp, formatUsd, formatUsdCompact } from '../api/format'
import { formatFraudLabelSummary, friendlyCaseLabel } from '../api/presentation'
import type { RecentAnomaly } from '../api/types'
import { DatasetLimitations, EvidenceCoverage, SignalKindBadge } from '../components/recent/Coverage'
import { EmptyState, ErrorState, LoadingState } from '../components/states'

function metricValue(container: Record<string, unknown> | undefined, key: string): number | null {
  const block = container?.[key]
  if (block && typeof block === 'object' && 'value' in block) {
    const value = (block as { value?: unknown }).value
    return typeof value === 'number' ? value : null
  }
  return typeof block === 'number' ? block : null
}

function barWidth(value: number | null, max: number): string {
  if (value == null || max <= 0) return '0%'
  return `${Math.min(100, Math.round((value / max) * 100))}%`
}

export function RecentOverviewPage() {
  const [benchmark, setBenchmark] = useState<Record<string, unknown> | null>(null)
  const [evaluation, setEvaluation] = useState<Record<string, unknown> | null>(null)
  const [anomalies, setAnomalies] = useState<RecentAnomaly[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([
      getRecentBenchmark(controller.signal),
      getRecentEvaluation(controller.signal),
      listRecentAnomalies(controller.signal),
    ])
      .then(([benchmarkData, evaluationData, anomalyData]) => {
        setBenchmark(benchmarkData)
        setEvaluation(evaluationData)
        setAnomalies(anomalyData.anomalies)
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setError(errorMessage(err))
      })
    return () => controller.abort()
  }, [])

  if (error) return <ErrorState title="RECENT PUBLIC DATA could not be loaded" message={error} />
  if (!benchmark || !evaluation) return <LoadingState label="Loading January 2026 derived artifacts…" />

  const measurements = (benchmark.measurements ?? {}) as Record<string, unknown>
  const fraudCount = metricValue(measurements, 'labelled_fraud_transactions')
  const lead = anomalies[0] ?? null
  const overlay = lead?.evaluation_overlay ?? null

  return (
    <div className="space-y-8">
      <header>
        <p className="font-mono text-[11px] tracking-[0.2em] text-brass uppercase">
          {RECENT_PUBLIC_DATA}
        </p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">{RECENT_DATASET_NAME}</h1>
        <p className="mt-2 max-w-2xl text-sm text-mute">
          Recent public online-banking transaction data collected in January 2026. Historical
          labels are used only for evaluation.
        </p>
        <p className="mt-2 text-xs text-mute">
          Source:{' '}
          <a className="text-brass hover:underline" href={ZENODO_RECENT_URL}>
            Zenodo record 20359708
          </a>
        </p>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5" aria-label="Observed dataset">
        <Metric
          label="Observed transactions"
          value={formatNumber(metricValue(measurements, 'total_transactions'))}
          hint="January collection"
          kind="observed"
        />
        <Metric
          label="Confirmed fraud"
          value={formatNumber(fraudCount)}
          hint="is_fraud overlay"
          kind="truth"
        />
        <Metric
          label="Fraud rate"
          value={formatPercent(metricValue(measurements, 'fraud_transaction_rate'))}
          hint="labelled fraud / observed transactions"
          kind="truth"
        />
        <Metric
          label="Observed transaction value"
          value={formatUsd(metricValue(measurements, 'total_amount_usd'))}
          hint="amount · USD"
          kind="observed"
        />
        <Metric
          label="Labelled fraud value"
          value={formatUsd(metricValue(measurements, 'labelled_fraud_amount_usd'))}
          hint="is_fraud overlay · USD"
          kind="truth"
        />
      </section>

      <section className="border border-line bg-panel px-4 py-4">
        <h2 className="text-lg font-semibold">Classifier evaluation status</h2>
        <p className="mt-2 text-sm">
          {((evaluation.methodology as { classifier_metrics_calculated?: boolean } | undefined)
            ?.classifier_metrics_calculated ??
            (evaluation.classifier_metrics_calculated as boolean | undefined)) === true
            ? 'Classifier metrics were calculated for this collection.'
            : 'Classifier precision, recall, F1, and PR-AUC are not calculated for January 2026.'}
        </p>
        <p className="mt-1 text-xs text-mute">
          {String(
            (evaluation.methodology as { reason?: string } | undefined)?.reason ||
              evaluation.reason ||
              'This adapter does not emit an independent fraud score that can be compared with is_fraud.',
          )}{' '}
          Source: data/real_2026/evaluation.json · EVALUATION
        </p>
      </section>

      <section>
        <h2 className="text-lg font-semibold">Independent fraud signals</h2>
        <p className="mt-1 text-sm text-mute">
          Hour-level volume and amount outliers derived from transaction fields only. Source
          CNN-LSTM outputs are not used.
        </p>
        <div className="mt-4 space-y-3">
          <Signal
            label="Fraud-rate overlay"
            width={barWidth(metricValue(measurements, 'fraud_transaction_rate'), 0.01)}
            kind="truth"
          />
          <Signal
            label="Temporal concentration"
            width={barWidth(lead?.live_score ?? null, 8)}
            kind="observed"
          />
          <Signal
            label="Amount concentration"
            width={barWidth(lead?.amount_usd ?? null, metricValue(measurements, 'total_amount_usd') ?? 1)}
            kind="observed"
          />
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold">Recent-data anomalies</h2>
        <p className="mt-1 text-sm text-mute">
          Temporal anomaly and amount concentration on calendar hours. is_fraud is not a live
          input.
        </p>
        {anomalies.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              title="No hour-level outliers above threshold"
              message="Volume and amount z-scores did not exceed the descriptive threshold."
            />
          </div>
        ) : (
          <div className="table-wrap mt-4 border border-line">
            <table className="w-full text-left text-sm">
              <thead className="bg-raised text-[11px] tracking-[0.12em] text-mute uppercase">
                <tr>
                  <th className="px-3 py-2 font-medium">Investigation</th>
                  <th className="px-3 py-2 font-medium">Temporal window</th>
                  <th className="px-3 py-2 font-medium">Observed</th>
                  <th className="px-3 py-2 font-medium">Signals</th>
                </tr>
              </thead>
              <tbody>
                {anomalies.map((item) => (
                  <tr key={item.anomaly_id} className="border-t border-line">
                    <td className="px-3 py-2">
                      <Link className="text-brass hover:underline" to={`/recent/anomalies/${item.anomaly_id}`}>
                        {item.kind}
                      </Link>
                      <p className="text-[11px] text-mute">{friendlyCaseLabel(item.anomaly_id)}</p>
                    </td>
                    <td className="px-3 py-2">{formatTimestamp(item.hour_start)}</td>
                    <td className="px-3 py-2">
                      {formatNumber(item.transactions)} txs · {formatUsdCompact(item.amount_usd)}
                    </td>
                    <td className="px-3 py-2 text-mute">{item.signals.join(', ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="border border-line bg-panel p-5">
        <h2 className="text-lg font-semibold">Investigation evidence</h2>
        {lead == null ? (
          <p className="mt-3 text-sm text-mute">
            No hour crossed the descriptive volume or amount threshold. Evidence is limited to
            collection-level observed counts above.
          </p>
        ) : (
          <ul className="mt-4 space-y-3 text-sm">
            <EvidenceRow
              title="Temporal window"
              detail={formatTimestamp(lead.hour_start)}
              kind="observed"
            />
            <EvidenceRow
              title="Transaction volume"
              detail={`${formatNumber(lead.transactions)} transactions`}
              kind="observed"
            />
            <EvidenceRow
              title="Transaction amount"
              detail={formatUsd(lead.amount_usd)}
              kind="observed"
            />
            <EvidenceRow
              title={overlay == null ? 'Fraud labels' : formatFraudLabelSummary(overlay.fraud_count, overlay.fraud_rate, lead.transactions).title}
              detail={
                overlay == null
                  ? 'No fraud labels for this hour'
                  : formatFraudLabelSummary(overlay.fraud_count, overlay.fraud_rate, lead.transactions).detail
              }
              kind="truth"
            />
          </ul>
        )}
      </section>

      <EvidenceCoverage />
      <DatasetLimitations />
    </div>
  )
}

function Metric({
  label,
  value,
  hint,
  kind,
}: {
  label: string
  value: string
  hint: string
  kind: 'observed' | 'proxy' | 'truth'
}) {
  return (
    <article className="border border-line bg-panel px-4 py-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[11px] tracking-[0.14em] text-mute uppercase">{label}</p>
        <SignalKindBadge kind={kind} />
      </div>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
      <p className="mt-2 text-[11px] text-mute">{hint}</p>
    </article>
  )
}

function Signal({
  label,
  width,
  kind,
}: {
  label: string
  width: string
  kind: 'observed' | 'proxy' | 'truth'
}) {
  return (
    <div>
      <div className="flex items-center gap-2">
        <p className="text-sm">{label}</p>
        <SignalKindBadge kind={kind} />
      </div>
      <div className="mt-1 h-2 bg-raised">
        <div className="h-2 bg-brass" style={{ width }} />
      </div>
    </div>
  )
}

function EvidenceRow({
  title,
  detail,
  kind,
}: {
  title: string
  detail: string
  kind: 'observed' | 'proxy' | 'truth'
}) {
  return (
    <li className="flex flex-wrap items-baseline justify-between gap-2 border-t border-line pt-3 first:border-0 first:pt-0">
      <div>
        <p className="font-medium">{title}</p>
        <p className="mt-0.5 text-mute">{detail}</p>
      </div>
      <SignalKindBadge kind={kind} />
    </li>
  )
}
