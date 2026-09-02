import { formatNumber, formatPercent, formatTimestamp } from './format'

const AUDIT_EVENT_LABELS: Record<string, string> = {
  CUSTOM_DECISION_RECORDED: 'Decision recorded',
  CUSTOM_ACTION_PROPOSED: 'Action proposed',
  CUSTOM_ACTION_APPROVED: 'Approval recorded',
  CUSTOM_ACTION_SIMULATED: 'Simulation completed',
  CUSTOM_RAZORPAY_TEST_SIMULATED: 'Razorpay test simulation completed',
  CUSTOM_RAZORPAY_TEST_FAILED: 'Razorpay test simulation failed',
  RECENT_DECISION_RECORDED: 'Decision recorded',
  RECENT_ACTION_PROPOSED: 'Action proposed',
  RECENT_ACTION_APPROVED: 'Approval recorded',
  RECENT_ACTION_SIMULATED: 'Simulation completed',
  RECENT_RAZORPAY_TEST_SIMULATED: 'Razorpay test simulation completed',
  RECENT_RAZORPAY_TEST_FAILED: 'Razorpay test simulation failed',
  IEEE_DECISION_RECORDED: 'Decision recorded',
  IEEE_ACTION_PROPOSED: 'Action proposed',
  IEEE_ACTION_APPROVED: 'Approval recorded',
  IEEE_ACTION_SIMULATED: 'Simulation completed',
  IEEE_RAZORPAY_TEST_SIMULATED: 'Razorpay test simulation completed',
  IEEE_RAZORPAY_TEST_FAILED: 'Razorpay test simulation failed',
  DECISION_RECORDED: 'Decision recorded',
  ACTION_PROPOSED: 'Action proposed',
  ACTION_APPROVED: 'Approval recorded',
  ACTION_SIMULATED: 'Simulation completed',
  ACTION_VERIFIED: 'Simulation verified',
  ACTION_SANDBOX_TEST_SIMULATED: 'Razorpay test simulation completed',
  ACTION_SANDBOX_TEST_FAILED: 'Razorpay test simulation failed',
}

const ACTION_TYPE_LABELS: Record<string, string> = {
  flag_for_human_review: 'Flag for human review',
  review_transactions: 'Review transactions',
  review_time_window: 'Review time window',
  monitor_only: 'Monitor only',
  flag_high_risk_transactions: 'Flag high-risk transactions',
  review_hour: 'Review time window',
  take_no_simulated_action: 'No simulated action',
  review: 'Review',
  monitor: 'Monitor',
  tighten_rule: 'Tighten rule',
  no_action: 'No action',
}

const SIMULATION_RESULTS: Record<string, string> = {
  flag_for_human_review: 'The anomaly would be placed into a human-review queue.',
  review_transactions: 'The flagged transactions would be queued for analyst review.',
  review_time_window: 'This time window would be queued for analyst review.',
  review_hour: 'This time window would be queued for analyst review.',
  monitor_only: 'The window would remain under observation. No review-queue change would be made.',
  flag_high_risk_transactions: 'High-risk transactions in this window would be queued for analyst review.',
  take_no_simulated_action: 'No operational change would be recorded.',
  review: 'The case would be queued for analyst review.',
  monitor: 'The window would remain under observation.',
  tighten_rule: 'The recommended rule tightening would be recorded in the simulation sandbox.',
  no_action: 'No operational change would be recorded.',
}

const ISO_TIMESTAMP = /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?/g

export function auditEventLabel(kind: string | null | undefined): string {
  const key = String(kind ?? '').trim()
  if (AUDIT_EVENT_LABELS[key]) return AUDIT_EVENT_LABELS[key]
  if (!key) return 'Audit event'
  return key
    .replaceAll('_', ' ')
    .toLowerCase()
    .replace(/^\w/, (char) => char.toUpperCase())
}

export function actionTypeLabel(actionType: string | null | undefined): string {
  const key = String(actionType ?? '').trim()
  if (ACTION_TYPE_LABELS[key]) return ACTION_TYPE_LABELS[key]
  if (!key) return 'Review action'
  return key.replaceAll('_', ' ').replace(/^\w/, (char) => char.toUpperCase())
}

export function actionRequestLabel(actionType: string | null | undefined): string {
  const key = String(actionType ?? '').trim()
  if (key === 'flag_for_human_review') return 'Flag this anomaly for human review'
  if (key === 'flag_high_risk_transactions') return 'Flag high-risk transactions in this window for review'
  if (key === 'review_time_window' || key === 'review_hour') return 'Review this time window'
  if (key === 'review_transactions') return 'Review the flagged transactions'
  if (key === 'monitor_only' || key === 'monitor') return 'Monitor this window only'
  return actionTypeLabel(actionType)
}

export function friendlyCaseLabel(
  id: string | null | undefined,
  noun: 'Anomaly' | 'Case' = 'Anomaly',
): string {
  const raw = String(id ?? '').trim()
  if (!raw) return noun
  const last = raw.split('-').filter(Boolean).at(-1) ?? ''
  const digits = last.replace(/\D/g, '')
  if (digits) return `${noun} #${String(Number(digits))}`
  return noun
}

export function friendlyAnomalyTitle(kind: string | null | undefined): string {
  const raw = String(kind ?? '').trim()
  const lower = raw.toLowerCase()
  if (!raw) return 'Detected anomaly'
  if (lower.includes('amount') || lower.includes('concentration')) {
    return 'Unusual transaction concentration'
  }
  if (lower.includes('temporal') || lower.includes('volume')) {
    return 'Unusual transaction activity'
  }
  if (lower.includes('entity')) return 'Unusual entity concentration'
  return raw.replaceAll('_', ' ').replace(/^\w/, (char) => char.toUpperCase())
}

export function inferGovernedActionType(input: {
  recorded?: string | null
  signals?: string[]
  fallback?: string | null
}): string {
  if (input.recorded) return input.recorded
  const text = (input.signals ?? []).join(' ').toLowerCase()
  if (text.includes('amount')) {
    return input.fallback === 'flag_high_risk_transactions'
      ? 'flag_high_risk_transactions'
      : 'flag_for_human_review'
  }
  if (text.includes('volume') || text.includes('concentration') || text.includes('temporal')) {
    return input.fallback === 'flag_high_risk_transactions' ? 'review_hour' : 'review_time_window'
  }
  return input.fallback || 'flag_for_human_review'
}

export function analysisMethodCopy(llmUsed: boolean): {
  headline: string
  detail: string
  secondary: string
} {
  if (llmUsed) {
    return {
      headline: 'Analysis method: Assisted review',
      detail:
        'This finding was produced using detection rules, then explained by a language model used only as a narrator. The language model is not the fraud classifier.',
      secondary: 'Generative AI was used only to explain this finding.',
    }
  }
  return {
    headline: 'Analysis method: Rule-based analysis',
    detail:
      'This finding was produced using deterministic detection rules and statistical checks. No AI/LLM was used to generate this explanation.',
    secondary: 'No generative AI was used for this finding.',
  }
}

export const SIMULATION_IMPACT_INTRO =
  'This simulation demonstrates the action that would be taken in a production fraud-response environment. No production payment, merchant-account change, or real-money movement is performed.'

export const RAZORPAY_TEST_SIMULATION_COPY =
  'Demonstrates the corresponding payment-system operation using Razorpay Test Mode. No real payment or money movement occurs.'

export function simulationOutcome(actionType?: string | null): {
  headline: string
  result: string
  impactIntro: string
  impact: string[]
} {
  const key = String(actionType ?? '').trim()
  return {
    headline: actionTypeLabel(actionType),
    result:
      SIMULATION_RESULTS[key] ??
      `The approved action (${actionTypeLabel(actionType)}) would be recorded as a dry-run.`,
    impactIntro: SIMULATION_IMPACT_INTRO,
    impact: [
      'Payment: Would block the flagged payment in a live deployment.',
      'Merchant account: Would apply the approved merchant-account action in a live deployment.',
      'Execution: Simulated only — no live payment is executed.',
      'Money movement: Simulated only — no real money is moved.',
    ],
  }
}

export function razorpayTestFromExecution(execution: unknown): Record<string, unknown> | null {
  if (!execution || typeof execution !== 'object') return null
  const record = execution as Record<string, unknown>
  const direct = record.razorpay_test
  if (direct && typeof direct === 'object' && !Array.isArray(direct)) {
    return direct as Record<string, unknown>
  }
  const verification = record.verification
  if (verification && typeof verification === 'object' && !Array.isArray(verification)) {
    const nested = (verification as Record<string, unknown>).sandbox_test
    if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
      return nested as Record<string, unknown>
    }
  }
  return null
}

export function simulationSafetyCopy(actionType?: string | null): {
  headline: string
  action: string
  detail: string
} {
  const outcome = simulationOutcome(actionType)
  return {
    headline: `Action simulated: ${outcome.headline}.`,
    action: outcome.headline,
    detail: `${outcome.result} ${outcome.impactIntro}`,
  }
}

export function decideWhyItMatters(actionType?: string | null): string {
  const key = String(actionType ?? '').trim()
  if (key === 'monitor_only' || key === 'monitor' || key === 'take_no_simulated_action') {
    return 'This pattern was identified as an anomaly that should stay under observation.'
  }
  if (key === 'review_time_window' || key === 'review_hour') {
    return 'This pattern was identified as an anomaly that warrants review of the time window.'
  }
  return 'This pattern was identified as an anomaly that warrants human investigation.'
}

export function auditEventNarrative(
  kind: string | null | undefined,
  actionType?: string | null,
): string {
  const key = String(kind ?? '')
  if (key.includes('DECISION')) return `System decision: ${actionTypeLabel(actionType)}`
  if (key.includes('PROPOSED')) return `Proposed action: ${actionRequestLabel(actionType)}`
  if (key.includes('APPROVED')) return 'Approval status: Approved'
  if (key.includes('RAZORPAY_TEST') || key.includes('SANDBOX_TEST')) {
    if (key.includes('FAILED')) return 'Result: Razorpay test simulation failed'
    return 'Result: Razorpay test simulation completed'
  }
  if (key.includes('SIMULATED') || key.includes('VERIFIED')) {
    return 'Result: Action simulated successfully'
  }
  return ''
}

export function formatFraudLabelSummary(
  fraudCount: number | null | undefined,
  fraudRate: number | null | undefined,
  transactionCount?: number | null,
): { title: string; detail: string } {
  const labelled = typeof fraudCount === 'number' && !Number.isNaN(fraudCount) ? fraudCount : 0
  let total: number | null =
    typeof transactionCount === 'number' && transactionCount > 0 ? transactionCount : null
  if (total == null && typeof fraudRate === 'number' && fraudRate > 0 && labelled > 0) {
    total = Math.round(labelled / fraudRate)
  }
  const ratePart =
    typeof fraudRate === 'number' && !Number.isNaN(fraudRate) ? ` (${formatPercent(fraudRate)})` : ''
  if (total != null) {
    return {
      title: 'Fraud labels',
      detail: `${formatNumber(labelled)} of ${formatNumber(total)} transactions labelled as fraud${ratePart}`,
    }
  }
  return {
    title: 'Fraud labels',
    detail: `${formatNumber(labelled)} ${labelled === 1 ? 'transaction' : 'transactions'} labelled as fraud${ratePart}`,
  }
}

export function evaluationMetricsCopy(
  reason: string | null | undefined,
  classifierMetricsCalculated?: boolean,
): { headline: string; detail: string; technical: string | null } {
  const raw = String(reason ?? '').trim()
  if (classifierMetricsCalculated) {
    return { headline: 'Fraud-model metrics', detail: raw, technical: null }
  }
  if (
    /evaluation-only|compatible IEEE score|compatible IEEE feature contract|classifier metrics/i.test(
      raw,
    )
  ) {
    return {
      headline: 'Fraud labels available for evaluation only',
      detail:
        'Your dataset contains fraud labels, but it does not contain the complete feature set required by the trained fraud-risk model. Fraud-model accuracy metrics are therefore unavailable.',
      technical: raw || 'Classifier metrics require a compatible IEEE score.',
    }
  }
  return { headline: 'Fraud labels', detail: raw, technical: null }
}

export function humanEvaluationReason(
  reason: string | null | undefined,
  classifierMetricsCalculated?: boolean,
): string {
  return evaluationMetricsCopy(reason, classifierMetricsCalculated).headline
}

export function humanizeEmbeddedTimestamps(text: string): string {
  return text.replace(ISO_TIMESTAMP, (match) => formatTimestamp(match))
}

export const CLASSIFIER_SCORED_REASONING =
  'Classifier output is available as supporting evidence.'
export const CLASSIFIER_UNSCORED_REASONING =
  'Classifier output was unavailable because the required feature coverage was not satisfied.'

const STALE_CLASSIFIER_CLAIM =
  /[^.]*((IEEE-CIS )?(supervised )?model (was|is) not applied|(IEEE-CIS )?classifier was not applied|This world has no supervised overlay|no supervised overlay from our trained model)[^.]*\.?/gi

export function classifierReasoningCopy(classifier: Record<string, unknown> | null | undefined): string {
  const status = typeof classifier?.status === 'string' ? classifier.status : ''
  if (status === 'scored') return CLASSIFIER_SCORED_REASONING
  if (status === 'not_scored') return CLASSIFIER_UNSCORED_REASONING
  return ''
}

export function sanitizeReasoningText(
  text: string | null | undefined,
  classifier?: Record<string, unknown> | null,
): string {
  void classifier
  return String(text ?? '')
    .replace(STALE_CLASSIFIER_CLAIM, '')
    .replace(/\s+/g, ' ')
    .trim()
}
