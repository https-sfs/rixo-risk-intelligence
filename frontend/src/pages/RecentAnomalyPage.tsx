import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  approveRecentAction,
  getRecentAnomaly,
  getRecentInvestigation,
  proposeRecentAction,
  simulateRecentAction,
} from '../api/client'
import {
  DEFAULT_OPERATOR,
  RECENT_DATASET_NAME,
  RECENT_PUBLIC_DATA,
  ZENODO_RECENT_URL,
} from '../api/constants'
import { errorMessage, formatNumber, formatPercent, formatTimestamp, formatUsd, formatUsdCompact } from '../api/format'
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
import { DatasetLimitations, EvidenceCoverage, SignalKindBadge } from '../components/recent/Coverage'
import { ErrorState, LoadingState } from '../components/states'

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {}
}

function labelledValue(block: unknown): unknown {
  return asRecord(block).value
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

export function RecentAnomalyPage() {
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
      getRecentAnomaly(anomalyId, signal),
      getRecentInvestigation(anomalyId, 'auto', signal),
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

  if (error) return <ErrorState title="Recent-data investigation could not be loaded" message={error} />
  if (!payload || !investigation) return <LoadingState label="Loading recent-data evidence artifact…" />

  const live = asRecord(payload.evidence.live_evidence)
  const overlay = asRecord(payload.evidence.evaluation_overlay)
  const hour = String(payload.anomaly.hour_start ?? labelledValue(live.temporal_window) ?? '')
  const txs = asNumber(labelledValue(live.transaction_count)) ?? asNumber(payload.anomaly.transactions)
  const amount = asNumber(labelledValue(live.amount_usd)) ?? asNumber(payload.anomaly.amount_usd)
  const kind = String(payload.anomaly.kind ?? 'Temporal anomaly')
  const anomalyTitle = friendlyAnomalyTitle(kind)
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
    fallback: 'flag_for_human_review',
  })

  async function onPropose() {
    setBusy('propose')
    setActionError(null)
    try {
      await proposeRecentAction(anomalyId)
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
      await approveRecentAction(String(proposal.action_id), DEFAULT_OPERATOR)
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
      await simulateRecentAction(String(proposal.action_id))
      await reloadCase()
    } catch (err: unknown) {
      setActionError(errorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  return (
    <article className="space-y-8">
      <Link to="/recent" className="text-sm text-brass hover:underline">
        ← Back to anomalies
      </Link>
      <header className="border border-line bg-panel px-5 py-5">
        <p className="font-mono text-[11px] tracking-[0.2em] text-brass uppercase">
          {RECENT_PUBLIC_DATA}
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">{RECENT_DATASET_NAME}</h1>
        <p className="mt-4 text-lg font-semibold">Anomaly: {anomalyTitle}</p>
        <p className="mt-1 text-sm">Period: {formatTimestamp(hour)}</p>
        <p className="mt-1 text-sm">
          {formatNumber(txs)} transactions · {formatUsdCompact(amount)} observed
        </p>
        <p className="mt-2 text-sm text-mute">
          Recent public online-banking transaction data collected in January 2026. Historical
          fraud labels are shown for this window.
        </p>
        <p className="mt-3 text-xs text-mute">
          Source:{' '}
          <a className="text-brass hover:underline" href={ZENODO_RECENT_URL}>
            Zenodo record 20359708
          </a>
        </p>
      </header>

      <InvestigatorIntelligence intelligence={payload.investigation_intelligence} />
      <InvestigationAgent agent={payload.investigation_agent} />

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Fact label="Transaction volume" value={formatNumber(txs)} kind="observed" />
        <Fact label="Transaction amount" value={formatUsd(amount)} kind="observed" />
        <Fact
          label="Observed fraud concentration"
          value={formatPercent(asNumber(overlay.fraud_rate))}
          kind="truth"
        />
        <Fact
          label="Confirmed fraud in window"
          value={formatNumber(asNumber(overlay.fraud_count))}
          kind="truth"
        />
      </section>

      <section className="border border-line bg-panel p-5">
        <h2 className="text-lg font-semibold">Investigation evidence</h2>
        <ul className="mt-4 space-y-3 text-sm">
          <EvidenceRow title="Temporal window" detail={formatTimestamp(hour)} kind="derived" />
          <EvidenceRow
            title="Transaction volume"
            detail={`${formatNumber(txs)} transactions`}
            kind="observed"
          />
          <EvidenceRow title="Transaction amount" detail={formatUsd(amount)} kind="observed" />
          <EvidenceRow
            title={labels.title}
            detail={labels.detail}
            kind="truth"
          />
        </ul>
        <p className="mt-4 text-xs text-mute">
          Source dataset model outputs were not used. This is not a live fraud detection claim.
        </p>
      </section>

      <ClassifierPanel classifier={classifierFromEvidence(payload.evidence)} />

      <section className="border border-line bg-panel p-5">
        <h2 className="text-lg font-semibold">Detection reasoning</h2>
        <p className="mt-1 text-xs text-mute">
          Explains why this window was detected from live January evidence. Classifier
          scores are reported separately and did not produce this finding.
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
        anomalyKind={kind}
        periodLabel={formatTimestamp(hour)}
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
        extraTechnical={[{ label: 'Dataset', value: RECENT_DATASET_NAME }]}
        backHref="/recent"
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
  kind: 'observed' | 'derived' | 'proxy' | 'truth'
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
  kind: 'observed' | 'derived' | 'proxy' | 'truth'
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
