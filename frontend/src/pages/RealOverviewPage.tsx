import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getRealBenchmark, getRealEvaluation, getRealModelEvaluation, getRealProfile, listRealAnomalies } from '../api/client'
import { MODEL_PREDICTION, REAL_PUBLIC_DATA } from '../api/constants'
import { errorMessage, formatNumber, formatPercent, formatUsd, formatUsdCompact } from '../api/format'
import { friendlyCaseLabel } from '../api/presentation'
import type { RealAnomaly } from '../api/types'
import { DatasetLimitations, EvidenceCoverage, SignalKindBadge } from '../components/real/Coverage'
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

function holdoutNumber(container: Record<string, unknown> | null, key: string): number | null {
  if (!container) return null
  const nested = container.temporal_holdout
  if (nested && typeof nested === 'object' && key in nested) {
    const value = (nested as Record<string, unknown>)[key]
    return typeof value === 'number' ? value : null
  }
  const value = container[key]
  return typeof value === 'number' ? value : null
}

export function RealOverviewPage() {
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null)
  const [benchmark, setBenchmark] = useState<Record<string, unknown> | null>(null)
  const [modelEval, setModelEval] = useState<Record<string, unknown> | null>(null)
  const [detectorEval, setDetectorEval] = useState<Record<string, unknown> | null>(null)
  const [anomalies, setAnomalies] = useState<RealAnomaly[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([
      getRealProfile(controller.signal),
      getRealBenchmark(controller.signal),
      listRealAnomalies(controller.signal),
      getRealModelEvaluation(controller.signal).catch(() => null),
      getRealEvaluation(controller.signal).catch(() => null),
    ])
      .then(([profileData, benchmarkData, anomalyData, modelData, evalData]) => {
        setProfile(profileData)
        setBenchmark(benchmarkData)
        setAnomalies(anomalyData.anomalies)
        setModelEval(modelData)
        setDetectorEval(evalData)
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setError(errorMessage(err))
      })
    return () => controller.abort()
  }, [])

  if (error) return <ErrorState title="REAL PUBLIC DATA could not be loaded" message={error} />
  if (!profile || !benchmark) return <LoadingState label="Loading IEEE-CIS derived artifacts…" />

  const measurements = (benchmark.measurements ?? {}) as Record<string, unknown>
  const identity = ((profile.identity_coverage ?? {}) as Record<string, unknown>).coverage
  const identityCoverage = typeof identity === 'number' ? identity : null
  const topProduct = Array.isArray(benchmark.by_product)
    ? (benchmark.by_product[0] as { labelled_fraud_rate?: number } | undefined)
    : undefined
  const fraudCount = metricValue(measurements, 'labelled_fraud_transactions')

  return (
    <div className="space-y-8">
      <header>
        <p className="font-mono text-[11px] tracking-[0.2em] text-brass uppercase">
          {REAL_PUBLIC_DATA}
        </p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">IEEE-CIS Fraud Detection</h1>
        <p className="mt-2 max-w-2xl text-sm text-mute">
          Historical e-commerce fraud analysis on the public IEEE-CIS tables. Amounts are USD.
        </p>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Observed dataset">
        <Metric
          label="Observed transactions"
          value={formatNumber(metricValue(measurements, 'total_transactions'))}
          hint="train_transaction.csv"
          kind="observed"
        />
        <Metric
          label="Fraud rate"
          value={formatPercent(metricValue(measurements, 'fraud_transaction_rate'))}
          hint={
            fraudCount == null
              ? 'isFraud overlay'
              : `${formatNumber(fraudCount)} labelled fraud transactions`
          }
          kind="truth"
        />
        <Metric
          label="Transaction value"
          value={formatUsd(metricValue(measurements, 'total_amount_usd'))}
          hint="TransactionAmt · USD"
          kind="observed"
        />
        <Metric
          label="Labelled fraud value"
          value={formatUsd(metricValue(measurements, 'labelled_fraud_amount_usd'))}
          hint="isFraud overlay · USD"
          kind="truth"
        />
      </section>

      <section>
        <h2 className="text-lg font-semibold">Fraud signals</h2>
        <p className="mt-1 text-sm text-mute">
          Observed volume, amount, ProductCD, and identity-join coverage from IEEE-CIS.
        </p>
        <div className="mt-4 space-y-3">
          <Signal
            label="Fraud-rate overlay"
            width={barWidth(metricValue(measurements, 'fraud_transaction_rate'), 0.1)}
            kind="truth"
          />
          <Signal
            label="Temporal concentration"
            width={barWidth(anomalies[0]?.live_score ?? null, 8)}
            kind="observed"
          />
          <Signal
            label="ProductCD concentration"
            width={barWidth(topProduct?.labelled_fraud_rate ?? null, 0.2)}
            kind="observed"
          />
          <Signal label="Identity coverage" width={barWidth(identityCoverage, 1)} kind="proxy" />
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold">Real-data anomalies</h2>
        <p className="mt-1 text-sm text-mute">
          Relative-hour outliers on volume, amount, and ProductCD. isFraud is not a live input.
        </p>
        {anomalies.length === 0 ? (
          <div className="mt-4">
            <EmptyState title="No anomalies in artifact" message="Run real-data preprocess." />
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
                      <Link className="text-brass hover:underline" to={`/real/anomalies/${item.anomaly_id}`}>
                        Temporal anomaly
                      </Link>
                      <p className="text-[11px] text-mute">{friendlyCaseLabel(item.anomaly_id)}</p>
                    </td>
                    <td className="px-3 py-2">
                      Relative hour {item.relative_hour_bucket}
                    </td>
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
        <p className="mt-3 text-xs text-mute">
          IEEE-CIS provides elapsed transaction time rather than calendar timestamps.
        </p>
      </section>

      <section className="border border-line bg-panel px-4 py-4">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold">Supervised fraud-risk layer</h2>
          <SignalKindBadge kind="model" />
        </div>
        <p className="mt-1 text-sm text-mute">
          Transaction-level IEEE-CIS classifier. {MODEL_PREDICTION} is not delayed ground truth
          and not an LLM score. Chronological 70/10/20 split; threshold frozen on validation;
          metrics below are the untouched temporal test set.
        </p>
        {modelEval == null ? (
          <p className="mt-3 text-sm text-mute">
            Model evaluation artifact is not available. Train with models.ieee_fraud.pipeline.
          </p>
        ) : (
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Metric
              label="Test PR-AUC"
              value={formatNumber((modelEval.ranking as { pr_auc?: number } | undefined)?.pr_auc ?? null)}
              hint="untouched temporal test vs isFraud"
              kind="model"
            />
            <Metric
              label="Test ROC-AUC"
              value={formatNumber((modelEval.ranking as { roc_auc?: number } | undefined)?.roc_auc ?? null)}
              hint="untouched temporal test vs isFraud"
              kind="model"
            />
            <Metric
              label="Test F1"
              value={formatNumber((modelEval.operating_point as { f1?: number } | undefined)?.f1 ?? null)}
              hint="frozen validation-selected threshold"
              kind="model"
            />
            <Metric
              label="Operating threshold"
              value={formatNumber((modelEval.operating_point as { threshold?: number } | undefined)?.threshold ?? null)}
              hint="selected on validation only"
              kind="model"
            />
            <Metric
              label="Test precision"
              value={formatPercent((modelEval.operating_point as { precision?: number } | undefined)?.precision ?? null)}
              hint="untouched temporal test vs isFraud"
              kind="model"
            />
            <Metric
              label="Test recall"
              value={formatPercent((modelEval.operating_point as { recall?: number } | undefined)?.recall ?? null)}
              hint="untouched temporal test vs isFraud"
              kind="model"
            />
            <Metric
              label="Test false positives"
              value={formatNumber(
                ((modelEval.operating_point as { confusion?: { fp?: number } } | undefined)?.confusion?.fp) ?? null,
              )}
              hint="operating_point.confusion · not an in-sample overlay"
              kind="model"
            />
            <Metric
              label="Test false negatives"
              value={formatNumber(
                ((modelEval.operating_point as { confusion?: { fn?: number } } | undefined)?.confusion?.fn) ?? null,
              )}
              hint="operating_point.confusion · not an in-sample overlay"
              kind="model"
            />
          </div>
        )}
      </section>

      {detectorEval ? (
        <section className="border border-line bg-panel px-4 py-4">
          <h2 className="text-lg font-semibold">Hour-detector holdout</h2>
          <p className="mt-1 text-sm text-mute">
            Hour-level detector versus delayed isFraud hours. This is not classifier test
            performance and not model accuracy.
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Metric
              label="Detector precision"
              value={formatPercent(holdoutNumber(detectorEval, 'precision'))}
              hint="data/real/evaluation.json temporal_holdout"
              kind="truth"
            />
            <Metric
              label="Detector recall"
              value={formatPercent(holdoutNumber(detectorEval, 'recall'))}
              hint="not classifier accuracy"
              kind="truth"
            />
          </div>
        </section>
      ) : null}

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
  kind: 'observed' | 'proxy' | 'truth' | 'model'
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
  kind: 'observed' | 'proxy' | 'truth' | 'model'
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
