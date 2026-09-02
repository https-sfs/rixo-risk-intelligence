import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  approveRealAction,
  getRealAnomaly,
  getRealInvestigation,
  proposeRealAction,
  simulateRealAction,
} from '../api/client'
import {
  DEFAULT_OPERATOR,
  MODEL_PREDICTION,
  REAL_PUBLIC_DATA,
} from '../api/constants'
import { errorMessage, formatNumber, formatPercent, formatUsd, formatUsdCompact } from '../api/format'
import {
  analysisMethodCopy,
  formatFraudLabelSummary,
  friendlyAnomalyTitle,
  humanizeEmbeddedTimestamps,
  inferGovernedActionType,
  sanitizeReasoningText,
} from '../api/presentation'
import type { InvestigationAgentResult, InvestigationIntelligence, RealInvestigation } from '../api/types'
import { ClassifierPanel, classifierFromEvidence } from '../components/ClassifierPanel'
import { InvestigationAgent } from '../components/InvestigationAgent'
import { InvestigatorIntelligence } from '../components/InvestigatorIntelligence'
import { GovernedActionWorkspace } from '../components/GovernedActionWorkspace'
import { DatasetLimitations, EvidenceCoverage, SignalKindBadge } from '../components/real/Coverage'
import { ErrorState, LoadingState } from '../components/states'

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {}
}

function labelledValue(block: unknown): unknown {
  const record = asRecord(block)
  return record.value
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && !Number.isNaN(value) ? value : null
}

function presentRecord(value: unknown): Record<string, unknown> | null {
  const record = asRecord(value)
  return Object.keys(record).length > 0 ? record : null
}

function governanceFromDetail(detail: { investigation_state?: unknown }): {
  decision: Record<string, unknown> | null
  proposal: Record<string, unknown> | null
  approval: Record<string, unknown> | null
  execution: Record<string, unknown> | null
  audit: Record<string, unknown>[]
} {
  const gov = asRecord(detail.investigation_state)
  const decision = presentRecord(gov.decision)
  const proposal = presentRecord(gov.proposal)
  const approval = presentRecord(gov.approval)
  const execution = presentRecord(gov.execution)
  return {
    decision,
    proposal: typeof proposal?.action_id === 'string' && proposal.action_id ? proposal : null,
    approval: approval?.approved === true || approval?.approved === false || approval?.action_id ? approval : null,
    execution: execution?.simulated === true || execution?.action_id ? execution : null,
    audit: Array.isArray(gov.audit) ? (gov.audit as Record<string, unknown>[]) : [],
  }
}

export function RealAnomalyPage() {
  const { anomalyId = '' } = useParams()
  const [payload, setPayload] = useState<{
    anomaly: Record<string, unknown>
    evidence: Record<string, unknown>
    investigation_state?: Record<string, unknown>
    investigation_intelligence?: InvestigationIntelligence | null
    investigation_agent?: InvestigationAgentResult | null
  } | null>(null)
  const [investigation, setInvestigation] = useState<RealInvestigation | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [decision, setDecision] = useState<Record<string, unknown> | null>(null)
  const [proposal, setProposal] = useState<Record<string, unknown> | null>(null)
  const [approval, setApproval] = useState<Record<string, unknown> | null>(null)
  const [execution, setExecution] = useState<Record<string, unknown> | null>(null)
  const [audit, setAudit] = useState<Record<string, unknown>[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  function applyGovernance(detail: { investigation_state?: unknown }) {
    const next = governanceFromDetail(detail)
    setDecision(next.decision)
    setProposal(next.proposal)
    setApproval(next.approval)
    setExecution(next.execution)
    setAudit(next.audit)
  }

  async function reloadCase(signal?: AbortSignal) {
    const [detail, report] = await Promise.all([
      getRealAnomaly(anomalyId, signal),
      getRealInvestigation(anomalyId, 'auto', signal),
    ])
    applyGovernance(detail)
    setPayload(detail)
    setInvestigation(report)
  }

  useEffect(() => {
    const controller = new AbortController()
    setPayload(null)
    setInvestigation(null)
    setDecision(null)
    setProposal(null)
    setApproval(null)
    setExecution(null)
    setAudit([])
    setError(null)
    reloadCase(controller.signal).catch((err: unknown) => {
      if (controller.signal.aborted) return
      setError(errorMessage(err))
    })
    return () => controller.abort()
  }, [anomalyId])

  if (error) return <ErrorState title="Real-data investigation could not be loaded" message={error} />
  if (!payload || !investigation) {
    return <LoadingState label="Loading real-data evidence artifact…" />
  }

  const live = asRecord(payload.evidence.live_evidence)
  const overlay = asRecord(payload.evidence.evaluation_overlay)
  const model = asRecord(payload.evidence.model_prediction)
  const product = asRecord(labelledValue(live.product_concentration))
  const card = asRecord(labelledValue(live.card_proxy_concentration))
  const addr = asRecord(labelledValue(live.address_proxy_concentration))
  const device = asRecord(labelledValue(live.device_proxy))
  const hour =
    asNumber(payload.anomaly.relative_hour_bucket) ??
    asNumber(asRecord(asRecord(labelledValue(live.temporal_anomaly)).value).relative_hour_bucket)
  const txs = asNumber(labelledValue(live.transaction_count))
  const amount = asNumber(labelledValue(live.amount_usd)) ?? asNumber(payload.anomaly.amount_usd)
  const topTransactions = Array.isArray(model.top_transactions)
    ? (model.top_transactions as Record<string, unknown>[])
    : []
  const sampleScope = typeof model.sample_scope === 'string' ? model.sample_scope : null
  const anomalyTitle = friendlyAnomalyTitle('Temporal anomaly')
  const labels = formatFraudLabelSummary(asNumber(overlay.fraud_count), asNumber(overlay.fraud_rate), txs)
  const method = analysisMethodCopy(investigation.llm_used)
  const recordedAction =
    typeof proposal?.action_type === 'string'
      ? proposal.action_type
      : typeof execution?.action_type === 'string'
        ? execution.action_type
        : null
  const actionType = inferGovernedActionType({
    recorded: recordedAction,
    signals: investigation.signals,
    fallback: 'flag_high_risk_transactions',
  })

  async function onPropose() {
    setBusy('propose')
    setActionError(null)
    try {
      await proposeRealAction(anomalyId)
      await reloadCase()
    } catch (err: unknown) {
      setActionError(errorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  async function onApprove() {
    if (!proposal) return
    setBusy('approve')
    setActionError(null)
    try {
      await approveRealAction(String(proposal.action_id), DEFAULT_OPERATOR)
      await reloadCase()
    } catch (err: unknown) {
      setActionError(errorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  async function onSimulate() {
    if (!proposal) return
    setBusy('simulate')
    setActionError(null)
    try {
      await simulateRealAction(String(proposal.action_id))
      await reloadCase()
    } catch (err: unknown) {
      setActionError(errorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  return (
    <article className="space-y-8">
      <Link to="/real" className="text-sm text-brass hover:underline">
        ← Back to anomalies
      </Link>
      <header className="border border-line bg-panel px-5 py-5">
        <p className="font-mono text-[11px] tracking-[0.2em] text-brass uppercase">
          {REAL_PUBLIC_DATA}
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">IEEE-CIS Fraud Detection</h1>
        <p className="mt-4 text-lg font-semibold">Anomaly: {anomalyTitle}</p>
        <p className="mt-1 text-sm">Period: Relative hour {hour ?? '—'}</p>
        <p className="mt-1 text-sm">
          {formatNumber(txs)} transactions · {formatUsdCompact(amount)} observed
        </p>
        <p className="mt-2 text-sm text-mute">
          IEEE-CIS provides elapsed transaction time rather than calendar timestamps.
        </p>
        <p className="mt-3 text-xs text-mute">{method.headline}</p>
      </header>

      <InvestigatorIntelligence intelligence={payload.investigation_intelligence} />
      <InvestigationAgent agent={payload.investigation_agent} />

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Fact
          label="Transaction volume"
          value={formatNumber(txs)}
          kind="observed"
        />
        <Fact
          label="Transaction amount"
          value={formatUsd(amount)}
          kind="observed"
        />
        <Fact
          label={labels.title}
          value={
            overlay.fraud_count != null
              ? labels.detail
              : formatPercent(asNumber(overlay.fraud_rate))
          }
          kind="truth"
        />
        <Fact
          label="Identity coverage"
          value={formatPercent(asNumber(labelledValue(live.identity_coverage)))}
          kind="proxy"
        />
      </section>

      <section className="border border-line bg-panel p-5">
        <h2 className="text-lg font-semibold">Investigation evidence</h2>
        <ul className="mt-4 space-y-3 text-sm">
          <EvidenceRow
            title="ProductCD concentration"
            detail={`${product.value ? String(product.value) : '—'} · share ${formatPercent(asNumber(product.share))}`}
            kind="derived"
          />
          <EvidenceRow
            title="Temporal concentration"
            detail={`Relative hour ${hour ?? '—'} · ${formatNumber(txs)} transactions · ${formatUsdCompact(amount)}`}
            kind="derived"
          />
          <EvidenceRow
            title="Card concentration"
            detail={card.value ? String(card.value) : '—'}
            kind="proxy"
          />
          <EvidenceRow
            title="Address concentration"
            detail={addr.value ? String(addr.value) : '—'}
            kind="proxy"
          />
          <EvidenceRow
            title="Device evidence"
            detail={device.value ? String(device.value) : '—'}
            kind="proxy"
          />
        </ul>
      </section>

      <ClassifierPanel
        classifier={classifierFromEvidence(payload.evidence)}
        sampleScope={sampleScope}
      />

      {Object.keys(model).length > 0 ? (
        <section className="border border-line bg-panel p-5">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold">Supervised fraud-risk overlay</h2>
            <SignalKindBadge kind="model" />
          </div>
          <p className="mt-1 text-sm text-mute">
            {MODEL_PREDICTION} from the IEEE-CIS classifier. Not delayed ground truth and not an
            LLM score.
            {sampleScope === 'IN_SAMPLE_MODEL_OVERLAY'
              ? ' This hour is an IN_SAMPLE_MODEL_OVERLAY — supporting evidence for this investigation. It is not held-out test performance, not model accuracy, and not production performance.'
              : sampleScope === 'OUT_OF_SAMPLE_MODEL_OVERLAY'
                ? ' This hour is an OUT_OF_SAMPLE_MODEL_OVERLAY (after the train TransactionDT cutoff). Still supporting evidence, not a published test-set score for this hour.'
                : ''}
          </p>
          <ul className="mt-4 space-y-3 text-sm">
            <EvidenceRow
              title="High-risk transactions in hour"
              detail={formatNumber(asNumber(model.high_risk_count))}
              kind="model"
            />
            <EvidenceRow
              title="Hour p95 score"
              detail={formatNumber(asNumber(model.p95_score))}
              kind="model"
            />
            <EvidenceRow
              title="Operating threshold"
              detail={formatNumber(asNumber(model.threshold))}
              kind="model"
            />
          </ul>
          {topTransactions.length > 0 ? (
            <ul className="mt-4 space-y-2 text-sm">
              {topTransactions.map((row) => (
                <li key={String(row.transaction_id)} className="border-t border-line pt-2 first:border-0 first:pt-0">
                  <p className="font-medium">
                    Transaction {String(row.transaction_id)} · score{' '}
                    {formatNumber(asNumber(row.fraud_risk_score))}
                  </p>
                  <p className="text-mute">
                    {MODEL_PREDICTION}
                    {typeof row.delayed_ground_truth === 'number'
                      ? ` · delayed ground truth ${row.delayed_ground_truth}`
                      : ''}
                  </p>
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}

      <section className="border border-line bg-panel p-5">
        <h2 className="text-lg font-semibold">Detection reasoning</h2>
        <p className="mt-1 text-xs text-mute">
          Explains why this relative hour was detected. Classifier overlay is supporting
          evidence only and is not the anomaly detector.
        </p>
        <p className="mt-1 text-sm font-medium">{method.headline}</p>
        <p className="mt-1 text-sm text-mute">{method.detail}</p>
        <p className="mt-1 text-sm text-mute">{method.secondary}</p>
        <p className="mt-3 text-sm">
          {humanizeEmbeddedTimestamps(
            sanitizeReasoningText(investigation.summary),
          )}
        </p>
      </section>

      <GovernedActionWorkspace
        actionType={actionType}
        anomalyKind="Temporal anomaly"
        periodLabel={`Relative hour ${hour ?? '—'}`}
        transactionCount={txs}
        amountLabel={amount != null ? formatUsd(amount) : null}
        fraudLabelCount={asNumber(overlay.fraud_count)}
        decision={decision}
        proposal={proposal}
        approval={approval}
        execution={execution}
        audit={audit}
        busy={busy}
        actionError={actionError}
        onPropose={() => void onPropose()}
        onApprove={() => void onApprove()}
        onSimulate={() => void onSimulate()}
        caseId={anomalyId}
        extraTechnical={[{ label: 'Dataset', value: 'IEEE-CIS Fraud Detection' }]}
        backHref="/real"
        backLabel="← Back to anomalies"
      />

      <EvidenceCoverage />
      <DatasetLimitations />
    </article>
  )
}

function Fact({
  label,
  value,
  kind,
}: {
  label: string
  value: string
  kind: 'observed' | 'derived' | 'proxy' | 'truth' | 'model'
}) {
  return (
    <div className="border border-line bg-panel px-4 py-3">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[11px] tracking-[0.12em] text-mute uppercase">{label}</p>
        <SignalKindBadge kind={kind} />
      </div>
      <p className="mt-1 text-xl font-semibold">{value}</p>
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
  kind: 'observed' | 'derived' | 'proxy' | 'truth' | 'model'
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
