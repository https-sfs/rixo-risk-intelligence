import type {
  ActionProposal,
  ActionState,
  Approval,
  AuditList,
  ExecutionResult,
  InvestigationAgentResult,
  InvestigationIntelligence,
  InvestigationResponse,
  Spike,
  SpikeList,
} from '../api/types'

export const COORD_ID = 'spk-coord-20260118-02'
export const FEST_ID = 'spk-fest-20260114-18'

export const coordSpike: Spike = {
  spike_id: COORD_ID,
  window_start: '2026-01-18T02:00:00',
  window_end: '2026-01-18T03:00:00',
  spike_type: 'suspicious_coordinated_spike',
  severity: 'high',
  volume: 75,
  baseline_volume: 4.889,
  volume_change_ratio: 15.341,
  fraud_rate: 0.84,
  baseline_fraud_rate: 0.016,
  failure_rate: 0.9067,
  unique_accounts: 43,
  unique_devices: 12,
  unique_ip_subnets: 5,
  unique_pincodes: 6,
  top_skus: [{ sku_id: 'sku_1050', count: 71 }],
  anomaly_reasons: ['ip_subnet_concentration'],
  anomaly_score: 65.834,
  coordination_score: 58.211,
}

export const festSpike: Spike = {
  ...coordSpike,
  spike_id: FEST_ID,
  spike_type: 'legitimate_festive_spike',
  severity: 'info',
  volume: 40,
  baseline_volume: 20,
  volume_change_ratio: 2,
  fraud_rate: 0.01,
  failure_rate: 0.02,
  coordination_score: 0.2,
}

export const spikeList: SpikeList = {
  spikes: [coordSpike, festSpike],
  count: 2,
  heldout_detection: {
    seed: 2027,
    provenance: 'EVALUATION',
    source: 'data/heldout/detection_metrics.json',
    evaluation_status: 'held-out seed 2027; not the seed-42 demo ledger',
    any_precision: 0.85,
    any_recall: 0.436,
    any_fp: 6,
    any_fn: 44,
  },
  heldout_investigation: {
    seed: 2027,
    provenance: 'EVALUATION',
    source: 'evaluation/investigation_metrics.json',
    accuracy: 0.85,
    n_detected_spikes: 40,
  },
}

export function sampleIntelligence(
  overrides: Partial<InvestigationIntelligence> = {},
): InvestigationIntelligence {
  return {
    world: 'SYNTHETIC SCENARIO',
    case_id: COORD_ID,
    classifier_status: {
      status: 'TRANSFERRED',
      headline: 'MODEL EVIDENCE: TRANSFERRED',
      detail:
        'The shared IEEE-CIS classifier was applied outside its native training and evaluation world. It is supporting evidence only. A high score is not a fraud confirmation.',
      kind: 'evidence_quality',
      not_a_fraud_verdict: true,
      not_a_governance_authorization: true,
      not_fraud_confirmed: true,
      not_the_anomaly_detector: true,
      not_the_action_decision: true,
    },
    brief: {
      why_flagged: ['Detector type: suspicious_coordinated_spike.'],
      what_supports_risk: ['Classifier High risk at 0.81. Supporting evidence only.'],
      observed: ['Window volume: 75 transactions.'],
      derived: ['Anomaly score: 65.834.'],
      uncertain: ['The IEEE-CIS classifier is transferred onto synthetic features.'],
      next_checks: ['Review the top reused device and the accounts sharing it.'],
      not_an_llm_paragraph: true,
    },
    temporal: {
      available: true,
      provenance: 'DERIVED',
      selected: { label: '2026-01-18T02:00:00' },
      neighbors: [
        { label: '2026-01-18T01:00:00', transaction_count: 8, is_selected: false },
        { label: '2026-01-18T02:00:00', transaction_count: 75, is_selected: true },
        { label: '2026-01-18T03:00:00', transaction_count: 9, is_selected: false },
      ],
      count_kind: 'OBSERVED',
      intensity_kind: 'DERIVED',
    },
    entities: {
      available: true,
      groups: {
        devices: [{ id: 'dev_5007', count: 40, provenance: 'OBSERVED' }],
      },
      missing: [],
    },
    baseline: {
      available: true,
      provenance: 'BASELINE',
      current: { volume: 75 },
      baseline: { volume: 5 },
      deviation: { ratio: 15, provenance: 'DERIVED' },
      definition: 'Synthetic hour-of-day baseline from data/hourly_windows.csv.',
    },
    case_metrics: [
      { label: 'Transactions', value: 75, provenance: 'OBSERVED', source: 'window.transaction_count' },
    ],
    false_positive_impact: {
      kind: 'operational_scenario',
      provenance: 'SCENARIO ASSUMPTION',
      monetary_estimate: null,
      not_money_saved: true,
      headline: 'Potential false-positive impact',
      note: 'If this case is a false positive, the recommended review would be unnecessary work.',
      impacts: [
        'Unnecessary human review of about 75 transactions in this window.',
        'Possible customer friction if a live review or rule change were later applied.',
      ],
    },
    classifier_is_not_detector: true,
    classifier_is_not_action: true,
    ...overrides,
  }
}

export function sampleAgent(
  overrides: Partial<InvestigationAgentResult> = {},
): InvestigationAgentResult {
  return {
    planner: 'deterministic_tool_plan',
    world: 'SYNTHETIC SCENARIO',
    case_id: COORD_ID,
    finding: 'Detector type: suspicious_coordinated_spike.',
    supporting_evidence: [
      {
        statement: 'Window volume: 75 transactions.',
        tool: 'inspect_case_metrics',
        provenance: 'OBSERVED',
      },
      {
        statement: 'Entity relationships are available for devices.',
        tool: 'inspect_entities',
        provenance: 'OBSERVED',
      },
    ],
    contradictory_evidence: [],
    uncertainty: [
      'MODEL EVIDENCE: TRANSFERRED — supporting evidence only. Not a fraud confirmation and not an action authorization.',
    ],
    recommended_next_human_check: 'Review the top reused device and the accounts sharing it.',
    evidence_used: [
      { tool: 'inspect_case_metrics', summary: 'Completed', limitations: [] },
      { tool: 'inspect_temporal_context', summary: 'Completed', limitations: [] },
      { tool: 'inspect_entities', summary: 'Completed', limitations: [] },
      { tool: 'inspect_historical_baseline', summary: 'Completed', limitations: [] },
      { tool: 'inspect_classifier_evidence', summary: 'Completed', limitations: [] },
    ],
    trace: [
      { tool: 'inspect_case_metrics', status: 'completed', label: 'inspect case metrics' },
      { tool: 'inspect_temporal_context', status: 'completed', label: 'inspect temporal context' },
      { tool: 'inspect_entities', status: 'completed', label: 'inspect entities' },
      { tool: 'inspect_historical_baseline', status: 'completed', label: 'inspect historical baseline' },
      { tool: 'inspect_classifier_evidence', status: 'completed', label: 'inspect classifier evidence' },
    ],
    tools: [
      'inspect_case_metrics',
      'inspect_temporal_context',
      'inspect_entities',
      'inspect_historical_baseline',
      'inspect_classifier_evidence',
    ],
    not_a_chatbot: true,
    not_a_governance_decision: true,
    does_not_authorize_action: true,
    read_only: true,
    ...overrides,
  }
}

export const coordInvestigation: InvestigationResponse = {
  provider: 'deterministic_reasoner',
  evidence_source: 'phase_2a_deterministic',
  report: {
    spike_id: COORD_ID,
    verdict: 'coordinated_abuse',
    confidence: 0.88,
    summary: 'Concentrated entities and failed payments indicate coordination.',
    supporting_evidence: [
      {
        fact: '94.67% of transactions share subnet 45.33.32.0/24',
        source: 'concentration.subnets.top_share',
      },
    ],
    contradicting_evidence: [
      {
        fact: 'A minority of accounts look ordinary shoppers.',
        source: 'diversity.accounts',
      },
    ],
    key_entities: [
      {
        entity_type: 'device',
        entity_id: 'dev_5007',
        reason: 'Highest reuse inside the window',
      },
    ],
    reasoning: 'Multiple independent concentration signals align.',
    recommended_action: {
      type: 'tighten_rule',
      scope: 'device dev_5007 within spike window',
      reason: 'Bound the likely replay device.',
    },
    human_approval_required: true,
    limitations: ['Window-only evidence'],
    provider: 'deterministic_reasoner',
  },
  classifier: {
    status: 'scored',
    fraud_risk_score: 0.81,
    classification: 'High risk',
    model: 'ieee_hgb',
    model_version: 2,
    feature_coverage: 0.015,
  },
  investigation_intelligence: sampleIntelligence(),
  investigation_agent: sampleAgent(),
}

export const festInvestigation: InvestigationResponse = {
  provider: 'deterministic_reasoner',
  evidence_source: 'phase_2a_deterministic',
  report: {
    ...coordInvestigation.report,
    spike_id: FEST_ID,
    verdict: 'likely_festive',
    confidence: 0.74,
    summary: 'Diverse successful traffic resembles festive shopping.',
    supporting_evidence: [
      { fact: 'Entity diversity is preserved.', source: 'diversity.devices' },
    ],
    contradicting_evidence: [
      { fact: 'Volume is elevated versus baseline.', source: 'window.volume_change_ratio' },
    ],
    recommended_action: {
      type: 'monitor',
      scope: 'window-level volume only; no entity block',
      reason: 'High volume with healthy outcomes.',
    },
    reasoning: 'Diversity and success outweigh coordination.',
  },
  investigation_intelligence: sampleIntelligence({
    case_id: FEST_ID,
    brief: {
      why_flagged: ['Detector type: legitimate_festive_spike.'],
      what_supports_risk: ['Classifier High risk at 0.608. Supporting evidence only.'],
      observed: ['Window volume: 40 transactions.'],
      derived: ['Anomaly score: 2.1.'],
      uncertain: ['The IEEE-CIS classifier is transferred onto synthetic features.'],
      next_checks: ['Treat the High-risk classifier label as supporting context, not a fraud confirmation.'],
    },
    false_positive_impact: {
      kind: 'operational_scenario',
      provenance: 'SCENARIO ASSUMPTION',
      monetary_estimate: null,
      not_money_saved: true,
      headline: 'Potential false-positive impact',
      note: 'The current recommendation is monitor-only, so a false positive would mainly create investigation time rather than a simulated rule change.',
      impacts: ['Possible operational workload for the risk team.'],
    },
  }),
  investigation_agent: sampleAgent({
    case_id: FEST_ID,
    finding: 'Detector type: legitimate_festive_spike.',
    uncertainty: [
      'MODEL EVIDENCE: LIMITED — supporting evidence only. Not a fraud confirmation and not an action authorization.',
    ],
    recommended_next_human_check:
      'Treat the High-risk classifier label as supporting context, not a fraud confirmation.',
  }),
}

export const proposal: ActionProposal = {
  action_id: 'act-1',
  spike_id: COORD_ID,
  action_type: 'tighten_rule',
  scope: 'device dev_5007 within spike window',
  reason: 'Bound the likely replay device.',
  source_provider: 'deterministic_reasoner',
  created_at: '2026-01-18T03:05:00Z',
  status: 'proposed',
  human_approval_required: true,
  verdict: 'coordinated_abuse',
}

export const approval: Approval = {
  action_id: 'act-1',
  approved: true,
  approved_by: 'analyst',
  approved_at: '2026-01-18T03:06:00Z',
  note: 'Approved from operator console',
}

export const execution: ExecutionResult = {
  action_id: 'act-1',
  status: 'simulated',
  simulated: true,
  affected_scope: 'device dev_5007 within spike window',
  message: 'SIMULATED: tighten_rule applied in demo sandbox',
  verification: {
    message: 'Simulation verified.',
    production_api_called: false,
    sandbox_test: {
      status: 'unavailable',
      provider: 'razorpay',
      environment: 'test',
      message: 'Razorpay test integration is unavailable (configuration missing).',
    },
  },
  audit_event_id: 'aud-3',
}

export function actionState(overrides: Partial<ActionState> = {}): ActionState {
  return {
    proposal,
    approval: null,
    execution: null,
    verification: null,
    ...overrides,
  }
}

export const emptyAudit: AuditList = { events: [], count: 0 }
