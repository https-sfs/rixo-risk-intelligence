import { formatNumber, formatPercent } from '../api/format'

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {}
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && !Number.isNaN(value) ? value : null
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function missingList(value: unknown): string {
  if (Array.isArray(value) && value.length > 0) {
    return value.map(String).slice(0, 12).join(', ')
  }
  return '—'
}

export function classifierFromEvidence(evidence: Record<string, unknown> | null | undefined): Record<string, unknown> | null {
  if (!evidence) return null
  const classifier = asRecord(evidence.classifier)
  if (classifier.status) return classifier
  const model = asRecord(evidence.model_prediction)
  if (!Object.keys(model).length) return null
  const score = asNumber(model.p95_score)
  const threshold = asNumber(model.threshold)
  if (score == null || threshold == null) return null
  return {
    status: 'scored',
    fraud_risk_score: score,
    classification: score >= threshold ? 'High risk' : 'Low risk',
    model: 'ieee_hgb',
    model_version: 2,
    feature_coverage: asNumber(model.feature_coverage),
    operating_threshold: threshold,
  }
}

export const CLASSIFIER_SUPPORTING_COPY =
  'Supporting evidence from the shared classifier. Independent of detection reasoning. Not an observed fraud label, not a payment decision, and not the anomaly detector.'

export const IN_SAMPLE_OVERLAY_COPY =
  'This hour is an IN_SAMPLE_MODEL_OVERLAY — supporting evidence for this investigation. It is not held-out test performance, not model accuracy, and not production performance.'

export function ClassifierPanel({
  classifier,
  sampleScope,
}: {
  classifier: Record<string, unknown> | null | undefined
  sampleScope?: string | null
}) {
  const block = asRecord(classifier)
  if (!block.status) return null

  const status = asString(block.status)
  const score = asNumber(block.fraud_risk_score)
  const classification = asString(block.classification)
  const model = asString(block.model) ?? 'ieee_hgb'
  const version = block.model_version ?? block.bundle_version
  const coverage = asNumber(block.feature_coverage)
  const reason = asString(block.reason)
  const missing = missingList(block.missing_features)
  const scope = sampleScope ?? asString(block.sample_scope)

  return (
    <section className="border border-line bg-panel p-5" data-testid="classifier-panel">
      <h2 className="text-lg font-semibold">Classifier evidence</h2>
      {status === 'not_scored' ? (
        <dl className="mt-4 space-y-2 text-sm">
          <div>
            <dt className="text-mute">Status</dt>
            <dd>Not scored</dd>
          </div>
          <div>
            <dt className="text-mute">Reason</dt>
            <dd>{reason ?? 'Required feature(s) unavailable'}</dd>
          </div>
          <div>
            <dt className="text-mute">Missing features</dt>
            <dd>{missing}</dd>
          </div>
        </dl>
      ) : (
        <dl className="mt-4 space-y-2 text-sm">
          <div>
            <dt className="text-mute">Fraud-risk score</dt>
            <dd>{score == null ? '—' : score.toFixed(2)}</dd>
          </div>
          <div>
            <dt className="text-mute">Classification</dt>
            <dd>{classification ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-mute">Model</dt>
            <dd>
              {model}
              {version != null ? ` · bundle ${String(version)}` : ''}
            </dd>
          </div>
          <div>
            <dt className="text-mute">Feature coverage</dt>
            <dd>{coverage == null ? '—' : formatPercent(coverage)}</dd>
          </div>
          {asNumber(block.high_risk_count) != null ? (
            <div>
              <dt className="text-mute">High-risk transactions</dt>
              <dd>{formatNumber(asNumber(block.high_risk_count))}</dd>
            </div>
          ) : null}
        </dl>
      )}
      <p className="mt-4 text-xs text-mute">{CLASSIFIER_SUPPORTING_COPY}</p>
      {scope === 'IN_SAMPLE_MODEL_OVERLAY' ? (
        <p className="mt-2 text-xs text-mute">{IN_SAMPLE_OVERLAY_COPY}</p>
      ) : null}
    </section>
  )
}
