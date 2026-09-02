import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  approveAction,
  executeAction,
  getAction,
  getInvestigation,
  getSpike,
  listAudit,
  proposeAction,
} from '../api/client'
import {
  DEFAULT_OPERATOR,
  DEMO_COORDINATED_SPIKE,
  DEMO_FESTIVE_SPIKE,
  SYNTHETIC_PROVENANCE,
} from '../api/constants'
import {
  errorMessage,
  formatConfidence,
  formatNumber,
  formatPercent,
  formatRatio,
  formatTimestamp,
  isPassiveAction,
  providerLabel,
  reasonList,
  skuSummary,
  verdictLabel,
} from '../api/format'
import {
  analysisMethodCopy,
  friendlyCaseLabel,
  humanizeEmbeddedTimestamps,
  sanitizeReasoningText,
} from '../api/presentation'
import type {
  ActionProposal,
  Approval,
  AuditEvent,
  ExecutionResult,
  InvestigationAgentResult,
  InvestigationIntelligence,
  InvestigationReport,
  InvestigationResponse,
  Spike,
} from '../api/types'
import { ClassifierPanel } from '../components/ClassifierPanel'
import { InvestigationAgent } from '../components/InvestigationAgent'
import { InvestigatorIntelligence } from '../components/InvestigatorIntelligence'
import { GovernedActionWorkspace } from '../components/GovernedActionWorkspace'
import { ErrorState, LoadingState } from '../components/states'
import { StatusBadge, severityTone, verdictTone } from '../components/StatusBadge'
import { useActionSession } from '../context/ActionSessionContext'

function presentRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function governanceFromInvestigation(investigation: InvestigationResponse): {
  decision: Record<string, unknown> | null
  proposal: ActionProposal | null
  approval: Approval | null
  execution: ExecutionResult | null
  audit: AuditEvent[]
} {
  const gov = investigation.investigation_state
  const decision = presentRecord(gov?.decision)
  const proposal = presentRecord(gov?.proposal)
  const approval = presentRecord(gov?.approval)
  const execution = presentRecord(gov?.execution)
  return {
    decision,
    proposal:
      typeof proposal?.action_id === 'string' && proposal.action_id
        ? (proposal as unknown as ActionProposal)
        : null,
    approval:
      approval?.approved === true || approval?.approved === false || approval?.action_id
        ? (approval as unknown as Approval)
        : null,
    execution:
      execution?.simulated === true || execution?.simulated === false || execution?.action_id
        ? (execution as unknown as ExecutionResult)
        : null,
    audit: Array.isArray(gov?.audit) ? (gov.audit as AuditEvent[]) : [],
  }
}

export function InvestigationDetailPage() {
  const { spikeId = '' } = useParams()
  const { rememberAction } = useActionSession()
  const [spike, setSpike] = useState<Spike | null>(null)
  const [report, setReport] = useState<InvestigationReport | null>(null)
  const [classifier, setClassifier] = useState<Record<string, unknown> | null>(null)
  const [intelligence, setIntelligence] = useState<InvestigationIntelligence | null>(null)
  const [agent, setAgent] = useState<InvestigationAgentResult | null>(null)
  const [provider, setProvider] = useState<string>('')
  const [loadError, setLoadError] = useState<string | null>(null)
  const [decision, setDecision] = useState<Record<string, unknown> | null>(null)
  const [proposal, setProposal] = useState<ActionProposal | null>(null)
  const [approval, setApproval] = useState<Approval | null>(null)
  const [execution, setExecution] = useState<ExecutionResult | null>(null)
  const [audit, setAudit] = useState<AuditEvent[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    setSpike(null)
    setReport(null)
    setClassifier(null)
    setIntelligence(null)
    setAgent(null)
    setLoadError(null)
    setDecision(null)
    setProposal(null)
    setApproval(null)
    setExecution(null)
    setAudit([])
    setActionError(null)
    Promise.all([
      getSpike(spikeId, controller.signal),
      getInvestigation(spikeId, 'deterministic', controller.signal),
    ])
      .then(([spikeData, investigation]) => {
        setSpike(spikeData)
        setReport(investigation.report)
        setClassifier(investigation.classifier ?? null)
        setIntelligence(investigation.investigation_intelligence ?? null)
        setAgent(investigation.investigation_agent ?? null)
        setProvider(investigation.provider)
        const restored = governanceFromInvestigation(investigation)
        setDecision(restored.decision)
        setProposal(restored.proposal)
        setApproval(restored.approval)
        setExecution(restored.execution)
        setAudit(restored.audit)
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setLoadError(errorMessage(err))
      })
    return () => controller.abort()
  }, [spikeId])

  async function refreshTrail(actionId: string) {
    const [state, events] = await Promise.all([
      getAction(actionId),
      listAudit({ action_id: actionId }),
    ])
    setProposal(state.proposal)
    setApproval(state.approval)
    setExecution(state.execution)
    setAudit(events.events)
    if (state.proposal) {
      setDecision({
        spike_id: state.proposal.spike_id,
        recorded_at: state.proposal.created_at,
        verdict: state.proposal.verdict,
        action_type: state.proposal.action_type,
      })
    }
  }

  async function onPropose() {
    if (!report) return
    setBusy('propose')
    setActionError(null)
    try {
      const created = await proposeAction(report)
      rememberAction(created.action_id)
      setProposal(created)
      await refreshTrail(created.action_id)
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
      const result = await approveAction(proposal.action_id, {
        approved_by: DEFAULT_OPERATOR,
        note: 'Approved from operator console',
      })
      setApproval(result)
      await refreshTrail(proposal.action_id)
    } catch (err: unknown) {
      setActionError(errorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  async function onExecute() {
    if (!proposal || !approval?.approved) {
      setActionError('Action is not approved. Human approval is required before simulation.')
      return
    }
    setBusy('simulate')
    setActionError(null)
    try {
      const result = await executeAction(proposal.action_id)
      setExecution(result)
      await refreshTrail(proposal.action_id)
    } catch (err: unknown) {
      setActionError(errorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  if (loadError) return <ErrorState title="Investigation unavailable" message={loadError} />
  if (!spike || !report) {
    return <LoadingState label="Loading spike metadata and deterministic investigation…" />
  }

  const recommended = report.recommended_action
  const festive = report.verdict === 'likely_festive'
  const caseLabel = friendlyCaseLabel(spike.spike_id, 'Case')
  const method = analysisMethodCopy(
    String(provider || report.provider)
      .toLowerCase()
      .includes('llm') &&
      !String(provider || report.provider)
        .toLowerCase()
        .includes('deterministic'),
  )

  return (
    <article className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <Link to="/investigations" className="text-brass hover:underline">
          ← Investigations
        </Link>
        <div className="flex flex-wrap gap-2">
          <Link className="min-h-11 rounded-md border border-line bg-panel px-3 py-2" to={`/investigations/${DEMO_COORDINATED_SPIKE}`}>
            Coordinated demo
          </Link>
          <Link className="min-h-11 rounded-md border border-line bg-panel px-3 py-2" to={`/investigations/${DEMO_FESTIVE_SPIKE}`}>
            Festive demo
          </Link>
        </div>
      </div>

      <header className="overflow-hidden border border-line bg-panel shadow-[0_1px_2px_rgba(23,43,77,0.04)]">
        <div
          className={
            report.verdict === 'coordinated_abuse'
              ? 'border-l-4 border-danger px-5 py-5'
              : report.verdict === 'likely_festive'
                ? 'border-l-4 border-success px-5 py-5'
                : 'border-l-4 border-warning px-5 py-5'
          }
        >
          <p className="font-mono text-[11px] tracking-[0.2em] text-mute uppercase">
            Fraud spike investigation
          </p>
          <p className="mt-2 font-mono text-[11px] tracking-[0.16em] text-brass uppercase">
            [{SYNTHETIC_PROVENANCE}]
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-navy md:text-3xl">{caseLabel}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <StatusBadge label={spike.severity} tone={severityTone(spike.severity)} />
            <span className="text-sm text-mute">{spike.spike_type.replaceAll('_', ' ')}</span>
            <span className="text-sm text-mute">{formatTimestamp(spike.window_start)}</span>
          </div>
          <div className="mt-6 flex flex-wrap items-end gap-6">
            <div>
              <p className="text-[11px] tracking-[0.16em] text-mute uppercase">Verdict</p>
              <p
                className={`text-3xl font-semibold uppercase ${
                  report.verdict === 'coordinated_abuse'
                    ? 'text-danger'
                    : report.verdict === 'likely_festive'
                      ? 'text-success'
                      : 'text-warning'
                }`}
              >
                {verdictLabel(report.verdict)}
              </p>
            </div>
            <div>
              <p className="text-[11px] tracking-[0.16em] text-mute uppercase">Confidence</p>
              <p className="text-3xl font-semibold">{formatConfidence(report.confidence)}</p>
            </div>
            <StatusBadge label={providerLabel(provider || report.provider)} />
          </div>
          {festive ? (
            <p className="mt-5 rounded-md border border-success/20 bg-[#ECFDF3] px-3 py-2 text-sm font-semibold tracking-wide text-success uppercase">
              High volume ≠ automatic fraud
            </p>
          ) : null}
        </div>
      </header>

      <InvestigatorIntelligence intelligence={intelligence} />
      <InvestigationAgent agent={agent} />

      <section aria-labelledby="summary-heading">
        <h2 id="summary-heading" className="text-lg font-semibold text-navy">
          Spike summary
        </h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Metric label="Volume" value={formatNumber(spike.volume)} />
          <Metric label="Volume vs baseline" value={formatRatio(spike.volume_change_ratio)} />
          <Metric label="Failure rate" value={formatPercent(spike.failure_rate)} />
          <Metric
            label="Labelled fraud rate"
            value={formatPercent(spike.fraud_rate)}
            hint="Historical fraud labels for this window"
          />
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <Metric label="Accounts" value={formatNumber(spike.unique_accounts)} />
          <Metric label="Devices" value={formatNumber(spike.unique_devices)} />
          <Metric label="IP subnets" value={formatNumber(spike.unique_ip_subnets)} />
          <Metric label="Pincodes" value={formatNumber(spike.unique_pincodes)} />
          <Metric label="SKUs" value={skuSummary(spike.top_skus)} />
        </div>
        {reasonList(spike.anomaly_reasons).length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {reasonList(spike.anomaly_reasons).map((reason) => (
              <StatusBadge key={reason} label={reason.replaceAll('_', ' ')} />
            ))}
          </div>
        ) : null}
      </section>

      <ClassifierPanel classifier={classifier} />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.9fr)]">
        <div className="space-y-6">
          <section className="border border-danger/30 bg-panel p-5">
            <h2 className="text-[12px] tracking-[0.16em] text-danger uppercase">
              Why this spike is suspicious
            </h2>
            <EvidenceList items={report.supporting_evidence} empty="No supporting evidence returned." />
          </section>
          <section className="border border-line bg-panel p-5">
            <h2 className="text-[12px] tracking-[0.16em] text-mute uppercase">
              What could explain this?
            </h2>
            <EvidenceList
              items={report.contradicting_evidence}
              empty="No material contradicting evidence identified."
            />
          </section>
          <section className="border border-line bg-panel p-5">
            <h2 className="text-[12px] tracking-[0.16em] text-mute uppercase">Key entities</h2>
            {report.key_entities.length === 0 ? (
              <p className="mt-3 text-sm text-mute">No key entities returned.</p>
            ) : (
              <ul className="mt-3 space-y-3">
                {report.key_entities.map((entity) => (
                  <li key={`${entity.entity_type}-${entity.entity_id}`} className="border-t border-line pt-3 first:border-0 first:pt-0">
                    <p className="text-[11px] tracking-[0.12em] text-mute uppercase">
                      {entity.entity_type}
                    </p>
                    <p className="font-mono text-sm">{entity.entity_id}</p>
                    <p className="mt-1 text-sm text-mute">{entity.reason}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <div className="space-y-6">
          <section className="border border-brass/40 bg-panel p-5">
            <h2 className="text-[12px] tracking-[0.16em] text-brass uppercase">
              Detection reasoning
            </h2>
            <p className="mt-2 text-xs text-mute">
              Explains why the anomaly was detected from operational evidence. Classifier
              scores are reported separately and did not produce this verdict.
            </p>
            <dl className="mt-4 space-y-3 text-sm">
              <div>
                <dt className="text-mute">Verdict</dt>
                <dd>
                  <StatusBadge
                    label={verdictLabel(report.verdict)}
                    tone={verdictTone(report.verdict)}
                  />
                </dd>
              </div>
              <div>
                <dt className="text-mute">Confidence</dt>
                <dd className="font-semibold">{formatConfidence(report.confidence)}</dd>
              </div>
              <div>
                <dt className="text-mute">Analysis method</dt>
                <dd className="font-semibold">{method.headline}</dd>
                <dd className="mt-1 text-mute">{method.detail}</dd>
                <dd className="mt-1 text-mute">{method.secondary}</dd>
              </div>
              <div>
                <dt className="text-mute">Summary</dt>
                <dd className="mt-1">
                  {humanizeEmbeddedTimestamps(sanitizeReasoningText(report.summary))}
                </dd>
              </div>
              <div>
                <dt className="text-mute">Reasoning</dt>
                <dd className="mt-1 whitespace-pre-wrap text-ink/90">
                  {sanitizeReasoningText(report.reasoning)}
                </dd>
              </div>
              <div>
                <dt className="text-mute">Limitations</dt>
                <dd>
                  {report.limitations.length === 0 ? (
                    <p className="mt-1 text-mute">None returned.</p>
                  ) : (
                    <ul className="mt-1 list-disc space-y-1 pl-5">
                      {report.limitations.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  )}
                </dd>
              </div>
            </dl>
          </section>

          {isPassiveAction(recommended) ? (
            <section className="border border-success/40 bg-success/10 p-5">
              <p className="text-sm font-semibold tracking-wide text-success uppercase">
                No tightening action recommended for this investigation. NO TIGHTEN_RULE.
              </p>
              <p className="mt-2 text-sm text-mute">{recommended.reason}</p>
            </section>
          ) : null}

          <GovernedActionWorkspace
            actionType={proposal?.action_type ?? recommended.type}
            anomalyKind={spike.spike_type.replaceAll('_', ' ')}
            periodLabel={formatTimestamp(spike.window_start)}
            transactionCount={spike.volume}
            amountLabel={null}
            decision={decision}
            proposal={proposal}
            approval={approval}
            execution={execution}
            audit={audit}
            busy={busy}
            actionError={actionError}
            onPropose={() => void onPropose()}
            onApprove={() => void onApprove()}
            onSimulate={() => void onExecute()}
            caseId={spike.spike_id}
            extraTechnical={[
              { label: 'Internal case ID', value: spike.spike_id },
              { label: 'Action ID', value: proposal?.action_id },
            ]}
            backHref="/investigations"
            backLabel="← Investigations"
          />
        </div>
      </div>
    </article>
  )
}

function Metric({
  label,
  value,
  hint,
}: {
  label: string
  value: string
  hint?: string
}) {
  return (
    <div className="border border-line bg-panel px-4 py-3">
      <p className="text-[11px] tracking-[0.12em] text-mute uppercase">{label}</p>
      <p className="mt-1 text-xl font-semibold">{value}</p>
      {hint ? <p className="mt-1 text-xs text-warning">{hint}</p> : null}
    </div>
  )
}

function EvidenceList({
  items,
  empty,
}: {
  items: { fact: string; source: string }[]
  empty: string
}) {
  if (items.length === 0) {
    return <p className="mt-3 text-sm text-mute">{empty}</p>
  }
  return (
    <ul className="mt-3 space-y-4">
      {items.map((item) => (
        <li key={`${item.source}-${item.fact}`}>
          <p className="text-sm font-medium">{item.fact}</p>
          <p className="mt-1 font-mono text-xs text-mute">Source: {item.source}</p>
        </li>
      ))}
    </ul>
  )
}
