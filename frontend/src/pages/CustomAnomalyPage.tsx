import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  approveCustomAction,
  getCustomAnomaly,
  getCustomInvestigation,
  proposeCustomAction,
  simulateCustomAction,
} from '../api/client'
import { rememberCustomSession } from '../api/customSession'
import {
  BRING_YOUR_DATA,
  DEFAULT_OPERATOR,
  SIMULATION_ONLY,
} from '../api/constants'
import { errorMessage, formatNumber, formatTemporalWindow } from '../api/format'
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

export function CustomAnomalyPage() {
  const { sessionId = '', anomalyId = '' } = useParams()
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
      getCustomAnomaly(sessionId, anomalyId, signal),
      getCustomInvestigation(sessionId, anomalyId, 'auto', signal),
    ])
    applyGovernance(detail)
    setPayload(detail)
    setInvestigation(report)
  }

  useEffect(() => {
    if (sessionId) rememberCustomSession(sessionId)
    const controller = new AbortController()
    setPayload(null)
    setInvestigation(null)
    setDecision(null)
    setProposal(null)
    setApproval(null)
    setExecution(null)
    setAudit([])
    setError(null)
    setActionError(null)
    reloadCase(controller.signal).catch((err: unknown) => {
      if (controller.signal.aborted) return
      setError(errorMessage(err))
    })
    return () => controller.abort()
  }, [sessionId, anomalyId])

  if (error) return <ErrorState title="Custom-data investigation could not be loaded" message={error} />
  if (!payload || !investigation) return <LoadingState label="Loading investigation evidence…" />

  const live = asRecord(payload.evidence.live_evidence)
  const overlay = asRecord(payload.evidence.evaluation_overlay)
  const hour = formatTemporalWindow(
    typeof payload.anomaly.time_display === 'string' ? payload.anomaly.time_display : String(labelledValue(live.temporal_window) ?? ''),
    String(payload.anomaly.hour_start ?? ''),
    typeof payload.anomaly.time_kind === 'string' ? payload.anomaly.time_kind : null,
  )
  const txs = asNumber(labelledValue(live.transaction_count)) ?? asNumber(payload.anomaly.transactions)
  const amount = asNumber(labelledValue(live.amount)) ?? asNumber(payload.anomaly.amount)
  const kind = String(payload.anomaly.kind ?? 'Custom-data anomaly')
  const anomalyTitle = friendlyAnomalyTitle(kind)
  const labels = formatFraudLabelSummary(
    asNumber(overlay.fraud_count),
    asNumber(overlay.fraud_rate),
    txs,
  )
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
      await proposeCustomAction(sessionId, anomalyId)
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
      await approveCustomAction(sessionId, String(proposal.action_id), DEFAULT_OPERATOR)
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
      await simulateCustomAction(sessionId, String(proposal.action_id))
      await reloadCase()
    } catch (err: unknown) {
      setActionError(errorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  const backHref = `/bring/${sessionId}`
  const amountLine =
    amount != null && !Number.isNaN(amount) ? ` · ${formatNumber(amount)} observed` : ''

  return (
    <article className="space-y-8">
      <Link to={backHref} className="text-sm text-brass hover:underline">
        ← Back to anomalies
      </Link>
      <header className="border border-line bg-panel px-5 py-5">
        <p className="font-mono text-[11px] tracking-[0.2em] text-brass uppercase">{BRING_YOUR_DATA}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">{anomalyTitle}</h1>
        <p className="mt-2 text-sm">{hour}</p>
        <p className="mt-1 text-sm">
          {formatNumber(txs)} transactions{amountLine}
        </p>
        <p className="mt-2 text-sm text-mute">
          User-provided dataset. Not mixed with the three benchmark worlds. {SIMULATION_ONLY}.
        </p>
      </header>

      <InvestigatorIntelligence intelligence={payload.investigation_intelligence} />
      <InvestigationAgent agent={payload.investigation_agent} />

      <section className="border border-line bg-panel p-5">
        <h2 className="text-lg font-semibold">Investigation evidence</h2>
        <ul className="mt-4 space-y-3 text-sm">
          <li>Temporal window · {hour}</li>
          <li>Transaction volume · {formatNumber(txs)}</li>
          {amount != null ? <li>Amount · {formatNumber(amount)}</li> : null}
          {overlay.fraud_count != null || overlay.label ? (
            <li>
              <p className="text-[11px] tracking-[0.12em] text-mute uppercase">
                {typeof overlay.label === 'string' && overlay.label
                  ? overlay.label
                  : 'USER-PROVIDED GROUND TRUTH'}
              </p>
              <p>{overlay.fraud_count != null ? labels.detail : 'User-provided labels are present for this window.'}</p>
              <p className="mt-1 text-xs text-mute">
                Evaluation only. Never treated as a model feature and never treated as the
                system&apos;s own fraud decision.
              </p>
            </li>
          ) : null}
        </ul>
      </section>

      <ClassifierPanel classifier={classifierFromEvidence(payload.evidence)} />

      <section className="border border-line bg-panel p-5">
        <h2 className="text-lg font-semibold">Detection reasoning</h2>
        <p className="mt-1 text-xs text-mute">
          Explains why this window was detected from the uploaded dataset. Classifier
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
        periodLabel={hour}
        transactionCount={txs}
        amountLabel={amount != null && !Number.isNaN(amount) ? formatNumber(amount) : null}
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
        extraTechnical={[
          { label: 'Session ID', value: sessionId },
          { label: 'Dataset', value: BRING_YOUR_DATA },
        ]}
        backHref={backHref}
        backLabel="← Back to anomalies"
      />
    </article>
  )
}
