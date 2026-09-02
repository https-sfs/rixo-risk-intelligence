import { expect, test } from 'vitest'
import { formatTimestamp } from './format'
import {
  actionTypeLabel,
  analysisMethodCopy,
  inferGovernedActionType,
  auditEventLabel,
  RAZORPAY_TEST_SIMULATION_COPY,
  SIMULATION_IMPACT_INTRO,
  simulationOutcome,
  CLASSIFIER_SCORED_REASONING,
  CLASSIFIER_UNSCORED_REASONING,
  evaluationMetricsCopy,
  friendlyAnomalyTitle,
  sanitizeReasoningText,
} from './presentation'

test('pre-proposal action type uses anomaly signals, not classifier high-risk count', () => {
  expect(
    inferGovernedActionType({
      signals: ['elevated transaction volume'],
      fallback: 'flag_high_risk_transactions',
    }),
  ).toBe('review_hour')
  expect(
    inferGovernedActionType({
      signals: ['elevated transaction amount'],
      fallback: 'flag_high_risk_transactions',
    }),
  ).toBe('flag_high_risk_transactions')
  expect(
    inferGovernedActionType({
      signals: ['elevated transaction volume'],
      fallback: 'flag_for_human_review',
    }),
  ).toBe('review_time_window')
  expect(
    inferGovernedActionType({
      signals: ['High risk'],
      fallback: 'monitor_only',
    }),
  ).toBe('monitor_only')
  expect(
    inferGovernedActionType({
      recorded: 'review_hour',
      signals: ['elevated transaction amount'],
    }),
  ).toBe('review_hour')
})

test('maps internal action and event codes to human labels', () => {
  expect(actionTypeLabel('flag_for_human_review')).toBe('Flag for human review')
  expect(auditEventLabel('CUSTOM_DECISION_RECORDED')).toBe('Decision recorded')
  expect(auditEventLabel('CUSTOM_ACTION_PROPOSED')).toBe('Action proposed')
  expect(auditEventLabel('CUSTOM_ACTION_APPROVED')).toBe('Approval recorded')
  expect(auditEventLabel('CUSTOM_ACTION_SIMULATED')).toBe('Simulation completed')
  expect(auditEventLabel('RECENT_RAZORPAY_TEST_SIMULATED')).toBe('Razorpay test simulation completed')
  expect(auditEventLabel('IEEE_RAZORPAY_TEST_FAILED')).toBe('Razorpay test simulation failed')
})

test('formats timestamps for local human display', () => {
  const formatted = formatTimestamp('2026-01-20T21:00:00')
  expect(formatted).toMatch(/20 Jan 2026/)
  expect(formatted).toMatch(/9:00 PM/)
  expect(formatted).not.toMatch(/2026-01-20T21:00:00/)
})

test('analysis method does not expose DETERMINISTIC as the headline', () => {
  const copy = analysisMethodCopy(false)
  expect(copy.headline).toBe('Analysis method: Rule-based analysis')
  expect(copy.detail).toMatch(/deterministic detection rules/)
  expect(copy.headline).not.toMatch(/DETERMINISTIC/)
})

test('evaluation copy keeps labels visible without implying they were ignored', () => {
  const copy = evaluationMetricsCopy(
    'User-provided labels are evaluation-only. Classifier metrics require a compatible IEEE score.',
    false,
  )
  expect(copy.headline).toBe('Fraud labels available for evaluation only')
  expect(copy.detail).toMatch(/contains fraud labels/)
  expect(copy.technical).toMatch(/compatible IEEE score/)
})

test('anomaly titles prefer a human description over an internal kind code', () => {
  expect(friendlyAnomalyTitle('amount_concentration')).toBe('Unusual transaction concentration')
})

test('reasoning sanitizer strips stale not-applied claims without injecting classifier copy', () => {
  const stale =
    'January 2026 window. The IEEE-CIS classifier was not applied. Detection used volume only.'
  expect(sanitizeReasoningText(stale, { status: 'scored' })).toBe(
    'January 2026 window. Detection used volume only.',
  )
  expect(sanitizeReasoningText(stale, { status: 'scored' })).not.toMatch(/classifier was not applied/i)
  expect(sanitizeReasoningText(stale, { status: 'scored' })).not.toContain(CLASSIFIER_SCORED_REASONING)
  expect(sanitizeReasoningText('Detection used volume only.', { status: 'not_scored' })).toBe(
    'Detection used volume only.',
  )
  expect(sanitizeReasoningText('Detection used volume only.', { status: 'not_scored' })).not.toContain(
    CLASSIFIER_UNSCORED_REASONING,
  )
})

test('classifier supporting-evidence copy stays on the classifier surface', () => {
  expect(CLASSIFIER_SCORED_REASONING).toBe('Classifier output is available as supporting evidence.')
  expect(auditEventLabel('DECISION_RECORDED')).toBe('Decision recorded')
})

test('simulation impact copy describes production capability without claiming live execution', () => {
  const outcome = simulationOutcome('flag_for_human_review')
  expect(outcome.impactIntro).toBe(SIMULATION_IMPACT_INTRO)
  expect(outcome.impact).toEqual([
    'Payment: Would block the flagged payment in a live deployment.',
    'Merchant account: Would apply the approved merchant-account action in a live deployment.',
    'Execution: Simulated only — no live payment is executed.',
    'Money movement: Simulated only — no real money is moved.',
  ])
  expect(RAZORPAY_TEST_SIMULATION_COPY).toMatch(/Razorpay Test Mode/)
  expect(RAZORPAY_TEST_SIMULATION_COPY).toMatch(/No real payment or money movement occurs/)
  expect(outcome.impact.join(' ')).not.toMatch(/payment would be blocked$/)
})
