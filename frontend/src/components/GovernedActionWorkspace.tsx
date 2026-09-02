import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { SIMULATION_ONLY } from '../api/constants'
import { formatNumber, formatTechnicalTimestamp, formatTimestamp } from '../api/format'
import {
  actionRequestLabel,
  actionTypeLabel,
  auditEventLabel,
  auditEventNarrative,
  decideWhyItMatters,
  friendlyAnomalyTitle,
  RAZORPAY_TEST_SIMULATION_COPY,
  razorpayTestFromExecution,
  simulationOutcome,
} from '../api/presentation'

export type GovernedPhase = 'decide' | 'approval' | 'simulate' | 'audit'

export type GovernedAuditEvent = Record<string, unknown>

const TABS: { id: GovernedPhase; label: string }[] = [
  { id: 'decide', label: 'Decision' },
  { id: 'approval', label: 'Approval' },
  { id: 'simulate', label: 'Simulation' },
  { id: 'audit', label: 'Audit history' },
]

function eventKind(event: GovernedAuditEvent): string {
  return String(event.kind ?? event.event_type ?? '')
}

function eventId(event: GovernedAuditEvent): string {
  return String(event.audit_event_id ?? event.event_id ?? `${eventKind(event)}-${event.timestamp ?? ''}`)
}

function eventTimestamp(event: GovernedAuditEvent): string {
  return typeof event.timestamp === 'string' ? event.timestamp : String(event.timestamp ?? '')
}

function approvalStatus(approval: Record<string, unknown> | null): 'PENDING' | 'APPROVED' | 'REJECTED' {
  if (!approval) return 'PENDING'
  if (approval.approved === false) return 'REJECTED'
  if (approval.approved === true) return 'APPROVED'
  return 'PENDING'
}

function currentPhase(
  proposal: Record<string, unknown> | null,
  approval: Record<string, unknown> | null,
  execution: Record<string, unknown> | null,
): GovernedPhase {
  if (execution?.simulated === true) return 'audit'
  if (approval?.approved === true) return 'simulate'
  if (proposal) return 'approval'
  return 'decide'
}

export function GovernedActionWorkspace({
  actionType,
  anomalyKind,
  periodLabel,
  transactionCount,
  amountLabel,
  fraudLabelCount,
  decision,
  proposal,
  approval,
  execution,
  audit,
  busy,
  actionError,
  onPropose,
  onApprove,
  onSimulate,
  caseId,
  extraTechnical = [],
  backHref,
  backLabel = '← Back to anomalies',
}: {
  actionType: string
  anomalyKind: string
  periodLabel: string
  transactionCount: number | null
  amountLabel: string | null
  fraudLabelCount?: number | null
  decision?: Record<string, unknown> | null
  proposal: Record<string, unknown> | null
  approval: Record<string, unknown> | null
  execution: Record<string, unknown> | null
  audit: GovernedAuditEvent[]
  busy: string | null
  actionError: string | null
  onPropose: () => void
  onApprove: () => void
  onSimulate: () => void
  caseId?: string | null
  extraTechnical?: Array<{ label: string; value: string | null | undefined }>
  backHref?: string | null
  backLabel?: string
}) {
  const phase = currentPhase(proposal, approval, execution)
  const [tab, setTab] = useState<GovernedPhase>(phase)

  useEffect(() => {
    setTab(phase)
  }, [phase])

  const decisionLabel = actionTypeLabel(actionType)
  const requestLabel = actionRequestLabel(actionType)
  const status = approvalStatus(approval)
  const simulated = execution?.simulated === true
  const outcome = simulationOutcome(actionType)
  const razorpayTest = razorpayTestFromExecution(execution)
  const approvedAt =
    typeof approval?.approved_at === 'string' ? formatTimestamp(approval.approved_at) : null
  const decisionRecordedAt =
    typeof decision?.recorded_at === 'string'
      ? formatTimestamp(decision.recorded_at)
      : typeof proposal?.created_at === 'string'
        ? formatTimestamp(proposal.created_at)
        : null
  const recorded = decision != null || proposal != null

  return (
    <section className="border border-line bg-panel p-5 shadow-[0_1px_2px_rgba(23,43,77,0.04)]">
      <p className="text-[11px] font-semibold tracking-[0.14em] text-brass uppercase">Governed action</p>
      <h2 className="mt-1 text-lg font-semibold text-navy">Investigation workflow</h2>
      <p className="mt-1 text-sm text-mute">
        1. Decision → 2. Approval → 3. Simulation → 4. Audit
      </p>
      <p className="mt-1 text-sm text-navy">
        Here is what RIXO recommends, why it requires human approval, the exact simulated action, and the audit trail.
      </p>
      <p className="mt-1 text-sm text-mute">
        {SIMULATION_ONLY}. TEST MODE ONLY. No real money is moved. Human approval is required.
      </p>
      {backHref ? (
        <p className="mt-3">
          <Link to={backHref} className="text-sm text-brass hover:underline">
            {backLabel}
          </Link>
        </p>
      ) : null}

      <div role="tablist" aria-label="Investigation workflow" className="mt-4 grid gap-2 sm:grid-cols-4">
        {TABS.map((item) => {
          const selected = item.id === tab
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              id={`governed-tab-${item.id}`}
              aria-selected={selected}
              aria-controls={`governed-panel-${item.id}`}
              onClick={() => setTab(item.id)}
              className={
                selected
                  ? 'min-h-11 rounded-md border border-brass bg-raised px-2 py-2 text-center text-sm font-semibold text-brass'
                  : 'min-h-11 rounded-md border border-line bg-panel px-2 py-2 text-center text-sm text-mute hover:text-navy'
              }
            >
              {item.label}
            </button>
          )
        })}
      </div>

      {actionError ? <p className="mt-3 text-sm text-danger">{actionError}</p> : null}

      <div
        role="tabpanel"
        id={`governed-panel-${tab}`}
        aria-labelledby={`governed-tab-${tab}`}
        className="mt-5"
      >
        {tab === 'decide' ? (
          <DecidePanel
            decisionLabel={decisionLabel}
            anomalyKind={anomalyKind}
            periodLabel={periodLabel}
            transactionCount={transactionCount}
            amountLabel={amountLabel}
            fraudLabelCount={fraudLabelCount}
            actionType={actionType}
            recorded={recorded}
            recordedAt={decisionRecordedAt}
            busy={busy}
            onPropose={onPropose}
          />
        ) : null}
        {tab === 'approval' ? (
          <ApprovalPanel
            requestLabel={requestLabel}
            status={status}
            approvedAt={approvedAt}
            hasProposal={proposal != null}
            busy={busy}
            onApprove={onApprove}
          />
        ) : null}
        {tab === 'simulate' ? (
          <SimulatePanel
            outcome={outcome}
            approved={status === 'APPROVED'}
            simulated={simulated}
            razorpayTest={razorpayTest}
            busy={busy}
            onSimulate={onSimulate}
          />
        ) : null}
        {tab === 'audit' ? (
          <AuditTimeline
            events={audit}
            actionType={actionType}
            caseId={caseId}
            extraTechnical={[
              ...extraTechnical,
              { label: 'Sandbox provider', value: razorpayTest ? String(razorpayTest.provider ?? 'razorpay') : null },
              { label: 'Sandbox environment', value: razorpayTest ? String(razorpayTest.environment ?? 'test') : null },
              {
                label: 'Razorpay test order',
                value: typeof razorpayTest?.test_order_id === 'string' ? razorpayTest.test_order_id : null,
              },
            ]}
          />
        ) : null}
      </div>
    </section>
  )
}

function DecidePanel({
  decisionLabel,
  anomalyKind,
  periodLabel,
  transactionCount,
  amountLabel,
  fraudLabelCount,
  actionType,
  recorded,
  recordedAt,
  busy,
  onPropose,
}: {
  decisionLabel: string
  anomalyKind: string
  periodLabel: string
  transactionCount: number | null
  amountLabel: string | null
  fraudLabelCount?: number | null
  actionType: string
  recorded: boolean
  recordedAt: string | null
  busy: string | null
  onPropose: () => void
}) {
  const title = friendlyAnomalyTitle(anomalyKind)
  return (
    <div className="space-y-4 text-sm">
      <div>
        <p className="text-[11px] tracking-[0.12em] text-mute uppercase">Decision</p>
        <p className="mt-1 text-xl font-semibold uppercase">{decisionLabel}</p>
      </div>
      <div>
        <p className="text-[11px] tracking-[0.12em] text-mute uppercase">Reason</p>
        <p className="mt-1">
          {title} was detected during {periodLabel}.
        </p>
      </div>
      <div>
        <p className="text-[11px] tracking-[0.12em] text-mute uppercase">Observed</p>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          {transactionCount != null ? <li>{formatNumber(transactionCount)} transactions</li> : null}
          {amountLabel ? <li>Total observed amount: {amountLabel}</li> : null}
          {fraudLabelCount != null ? (
            <li>
              {formatNumber(fraudLabelCount)} user-provided fraud{' '}
              {fraudLabelCount === 1 ? 'label' : 'labels'} in this window
            </li>
          ) : null}
        </ul>
      </div>
      <div>
        <p className="text-[11px] tracking-[0.12em] text-mute uppercase">Why it matters</p>
        <p className="mt-1">{decideWhyItMatters(actionType)}</p>
        <p className="mt-2 text-mute">
          The counts above are observed facts. The decision is an interpretation of those facts.
        </p>
      </div>
      {!recorded ? (
        <button
          type="button"
          onClick={onPropose}
          disabled={busy != null}
          className="w-full bg-ink px-4 py-2.5 text-sm font-semibold text-canvas disabled:opacity-50"
        >
          {busy === 'propose' ? 'Recording decision…' : 'Record this decision'}
        </button>
      ) : (
        <div className="border border-line bg-raised px-3 py-3">
          <p className="text-[11px] tracking-[0.12em] text-mute uppercase">Decision recorded</p>
          <p className="mt-1 font-semibold">{recordedAt ?? 'Recorded'}</p>
        </div>
      )}
    </div>
  )
}

function ApprovalPanel({
  requestLabel,
  status,
  approvedAt,
  hasProposal,
  busy,
  onApprove,
}: {
  requestLabel: string
  status: 'PENDING' | 'APPROVED' | 'REJECTED'
  approvedAt: string | null
  hasProposal: boolean
  busy: string | null
  onApprove: () => void
}) {
  return (
    <div className="space-y-4 text-sm">
      <div>
        <p className="text-[11px] tracking-[0.12em] text-mute uppercase">Approval required</p>
        <p className="mt-1 text-xl font-semibold">YES</p>
      </div>
      <div>
        <p className="text-[11px] tracking-[0.12em] text-mute uppercase">Requested action</p>
        <p className="mt-1 font-semibold">{requestLabel}</p>
      </div>
      <div>
        <p className="text-[11px] tracking-[0.12em] text-mute uppercase">Current status</p>
        <p className="mt-1 text-xl font-semibold">{hasProposal ? status : 'PENDING'}</p>
      </div>
      {!hasProposal ? (
        <p className="text-mute">A decision must be recorded before approval can be granted.</p>
      ) : null}
      {hasProposal && status === 'PENDING' ? (
        <button
          type="button"
          onClick={onApprove}
          disabled={busy != null}
          className="btn-primary w-full disabled:opacity-50"
        >
          {busy === 'approve' ? 'Approving…' : 'Approve'}
        </button>
      ) : null}
      {status === 'APPROVED' ? (
        <div className="border border-line bg-raised px-3 py-3">
          <p className="text-[11px] tracking-[0.12em] text-mute uppercase">Approval recorded</p>
          <p className="mt-1 font-semibold">{approvedAt ?? 'Recorded'}</p>
          <p className="mt-3 text-[11px] tracking-[0.12em] text-mute uppercase">Approved action</p>
          <p className="mt-1">{requestLabel}</p>
        </div>
      ) : null}
    </div>
  )
}

function SimulatePanel({
  outcome,
  approved,
  simulated,
  razorpayTest,
  busy,
  onSimulate,
}: {
  outcome: ReturnType<typeof simulationOutcome>
  approved: boolean
  simulated: boolean
  razorpayTest: Record<string, unknown> | null
  busy: string | null
  onSimulate: () => void
}) {
  const razorpayStatus = typeof razorpayTest?.status === 'string' ? razorpayTest.status : null
  const razorpayMessage =
    typeof razorpayTest?.message === 'string' ? razorpayTest.message : null
  const testOrderId =
    typeof razorpayTest?.test_order_id === 'string' ? razorpayTest.test_order_id : null
  return (
    <div className="space-y-4 text-sm">
      <div>
        <p className="text-[11px] tracking-[0.12em] text-mute uppercase">Simulation</p>
        <p className="mt-1 text-xl font-semibold uppercase">{outcome.headline}</p>
        <p className="mt-1 text-mute">This is a dry-run. No live payment action is performed.</p>
        <p className="mt-2 rounded-md border border-warning/20 bg-[#FFF7ED] px-3 py-2 text-[11px] font-semibold tracking-[0.12em] text-warning uppercase">
          TEST MODE ONLY — no real money is moved. Human approval is required.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="border border-line bg-raised px-3 py-3">
          <p className="text-[11px] tracking-[0.12em] text-mute uppercase">Internal simulation</p>
          <p className="mt-2 font-semibold">{simulated ? 'Completed' : 'Not run'}</p>
          <p className="mt-1 text-mute">{outcome.result}</p>
        </div>
        <div className="border border-line bg-raised px-3 py-3">
          <p className="text-[11px] tracking-[0.12em] text-mute uppercase">Razorpay TEST simulation</p>
          <p className="mt-2 font-semibold">
            {razorpayStatus === 'completed'
              ? 'Razorpay test simulation'
              : razorpayStatus === 'unavailable'
                ? 'Unavailable — configuration missing'
                : razorpayStatus === 'failed' || razorpayStatus === 'blocked'
                  ? 'Failed'
                  : 'Not run'}
          </p>
          <p className="mt-1 text-mute">{RAZORPAY_TEST_SIMULATION_COPY}</p>
          {razorpayMessage &&
          (razorpayStatus === 'unavailable' ||
            razorpayStatus === 'failed' ||
            razorpayStatus === 'blocked') ? (
            <p className="mt-1 text-mute">{razorpayMessage}</p>
          ) : null}
          {testOrderId ? (
            <p className="mt-2 font-mono text-xs text-mute">Test order: {testOrderId}</p>
          ) : null}
        </div>
      </div>
      <div>
        <p className="text-[11px] tracking-[0.12em] text-mute uppercase">Simulation impact</p>
        <p className="mt-1 text-mute">{outcome.impactIntro}</p>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          {outcome.impact.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </div>
      <div>
        <p className="text-[11px] tracking-[0.12em] text-mute uppercase">Status</p>
        <p className="mt-1 text-xl font-semibold">{simulated ? 'SIMULATION COMPLETED' : 'NOT SIMULATED'}</p>
      </div>
      {!approved ? (
        <p className="text-mute">Human approval is required before this dry-run can be recorded.</p>
      ) : null}
      {approved && !simulated ? (
        <button
          type="button"
          onClick={onSimulate}
          disabled={busy != null}
          className="btn-primary w-full disabled:opacity-50"
        >
          {busy === 'simulate' ? 'Simulating…' : 'Run dry-run simulation'}
        </button>
      ) : null}
    </div>
  )
}

function AuditTimeline({
  events,
  actionType,
  caseId,
  extraTechnical,
}: {
  events: GovernedAuditEvent[]
  actionType: string
  caseId?: string | null
  extraTechnical: Array<{ label: string; value: string | null | undefined }>
}) {
  return (
    <div className="space-y-4 text-sm">
      <p className="text-[11px] tracking-[0.12em] text-mute uppercase">Audit history</p>
      {events.length === 0 ? (
        <p className="text-mute">No audit events have been recorded yet.</p>
      ) : (
        <ol className="space-y-3">
          {events.map((event) => {
            const kind = eventKind(event)
            const narrative = auditEventNarrative(kind, actionType)
            return (
              <li key={eventId(event)} className="border-t border-line pt-3">
                <p className="font-semibold">{auditEventLabel(kind)}</p>
                <p className="mt-1 text-mute">{formatTimestamp(eventTimestamp(event))}</p>
                {narrative ? <p className="mt-1">{narrative}</p> : null}
              </li>
            )
          })}
        </ol>
      )}
      <details className="border border-line bg-raised/40 px-3 py-2">
        <summary className="cursor-pointer text-sm font-medium">Technical details</summary>
        <ul className="mt-3 space-y-2 font-mono text-xs text-mute">
          {caseId ? <li>Technical anomaly ID: {caseId}</li> : null}
          {extraTechnical.map((row) =>
            row.value ? (
              <li key={row.label}>
                {row.label}: {row.value}
              </li>
            ) : null,
          )}
          {events.map((event) => (
            <li key={`${eventId(event)}-tech`} className="border-t border-line pt-2">
              <p>Event code: {eventKind(event)}</p>
              <p>UTC timestamp: {formatTechnicalTimestamp(eventTimestamp(event))}</p>
              {event.audit_event_id || event.event_id ? (
                <p>Event ID: {String(event.audit_event_id ?? event.event_id)}</p>
              ) : null}
            </li>
          ))}
        </ul>
      </details>
    </div>
  )
}
