export type HealthResponse = {
  status: string
  service: string
  component: string
}

export type Spike = {
  spike_id: string
  window_start: string
  window_end: string
  spike_type: string
  severity: string
  volume: number
  baseline_volume: number | null
  volume_change_ratio: number | null
  fraud_rate: number
  baseline_fraud_rate: number | null
  failure_rate: number
  unique_accounts: number
  unique_devices: number
  unique_ip_subnets: number
  unique_pincodes: number
  top_skus: unknown
  anomaly_reasons: unknown
  anomaly_score: number
  coordination_score: number
}

export type SpikeList = {
  spikes: Spike[]
  count: number
  heldout_detection?: Record<string, unknown> | null
  heldout_investigation?: Record<string, unknown> | null
}

export type EvidenceItem = {
  fact: string
  source: string
}

export type KeyEntity = {
  entity_type: string
  entity_id: string
  reason: string
}

export type RecommendedAction = {
  type: string
  scope: string
  reason: string
}

export type InvestigationReport = {
  spike_id: string
  verdict: string
  confidence: number
  summary: string
  supporting_evidence: EvidenceItem[]
  contradicting_evidence: EvidenceItem[]
  key_entities: KeyEntity[]
  reasoning: string
  recommended_action: RecommendedAction
  human_approval_required: boolean
  limitations: string[]
  provider: string
}

export type InvestigationResponse = {
  report: InvestigationReport
  evidence_source: string
  provider: string
  classifier?: Record<string, unknown> | null
  investigation_intelligence?: InvestigationIntelligence | null
  investigation_agent?: InvestigationAgentResult | null
  investigation_state?: {
    decision?: Record<string, unknown> | null
    proposal?: ActionProposal | Record<string, unknown> | null
    approval?: Approval | Record<string, unknown> | null
    execution?: ExecutionResult | Record<string, unknown> | null
    audit?: AuditEvent[]
    status?: Record<string, unknown>
  } | null
}

export type ActionProposal = {
  action_id: string
  spike_id: string
  action_type: string
  scope: string
  reason: string
  source_provider: string
  created_at: string
  status: string
  human_approval_required: boolean
  verdict: string
}

export type Approval = {
  action_id: string
  approved: boolean
  approved_by: string
  approved_at: string
  note: string
}

export type ExecutionResult = {
  action_id: string
  status: string
  simulated: boolean
  affected_scope: string
  message: string
  verification: Record<string, unknown>
  audit_event_id: string
}

export type ActionState = {
  proposal: ActionProposal
  approval: Approval | null
  execution: ExecutionResult | null
  verification: Record<string, unknown> | null
}

export type AuditEvent = {
  event_id: string
  timestamp: string
  action_id: string
  spike_id: string
  event_type: string
  actor: string
  details: Record<string, unknown>
}

export type AuditList = {
  events: AuditEvent[]
  count: number
}

export type ProvenancedMetric = {
  value?: unknown
  provenance?: string
  source?: string
  evaluation_status?: string
  label?: string
}

export type InvestigationIntelligence = {
  world?: string
  case_id?: string
  classifier_status?: {
    status?: string
    headline?: string
    detail?: string
    kind?: string
    not_a_fraud_verdict?: boolean
    not_a_governance_authorization?: boolean
    not_fraud_confirmed?: boolean
    not_the_anomaly_detector?: boolean
    not_the_action_decision?: boolean
    used_for_action_selection?: boolean
    coverage_not_upgraded_by_scored_rows?: boolean
    feature_coverage?: number | null
    sample_scope?: string | null
    world?: string
    provenance?: string
  }
  brief?: {
    why_flagged?: string[]
    what_supports_risk?: string[]
    observed?: string[]
    derived?: string[]
    uncertain?: string[]
    next_checks?: string[]
    not_an_llm_paragraph?: boolean
  }
  temporal?: {
    available?: boolean
    reason?: string
    provenance?: string
    source?: string
    selected?: Record<string, unknown>
    neighbors?: Array<{
      label?: string
      transaction_count?: number | null
      amount?: number | null
      intensity?: number | null
      is_selected?: boolean
    }>
    baseline_note?: string
    count_kind?: string
    amount_kind?: string
    intensity_kind?: string
  }
  entities?: {
    available?: boolean
    provenance?: string
    groups?: Record<string, Array<Record<string, unknown>>>
    missing?: string[]
    note?: string
  }
  baseline?: {
    available?: boolean
    reason?: string
    provenance?: string
    current?: Record<string, unknown>
    baseline?: Record<string, unknown>
    deviation?: Record<string, unknown> | null
    definition?: string
  }
  case_metrics?: ProvenancedMetric[]
  false_positive_impact?: {
    kind?: string
    provenance?: string
    monetary_estimate?: number | null
    not_money_saved?: boolean
    headline?: string
    note?: string
    impacts?: string[]
    review_workload?: ProvenancedMetric
  }
  not_money_saved?: boolean
  classifier_is_not_detector?: boolean
  classifier_is_not_action?: boolean
}

export type InvestigationAgentEvidence = {
  statement?: string
  tool?: string
  provenance?: string
}

export type InvestigationAgentResult = {
  planner?: string
  world?: string
  case_id?: string
  finding?: string
  supporting_evidence?: InvestigationAgentEvidence[]
  contradictory_evidence?: InvestigationAgentEvidence[]
  uncertainty?: string[]
  recommended_next_human_check?: string
  evidence_used?: Array<{ tool?: string; summary?: string; limitations?: string[] }>
  trace?: Array<{ tool?: string; status?: string; label?: string }>
  tools?: string[]
  not_a_chatbot?: boolean
  not_a_governance_decision?: boolean
  does_not_authorize_action?: boolean
  read_only?: boolean
}

export type InvestigationProvider = 'deterministic' | 'llm'

export type RealWorldStatus = {
  world: string
  dataset: string
  raw_train_present: boolean
  artifacts: Record<string, boolean>
  ready: boolean
  amount_currency: string
}

export type RealAnomaly = {
  anomaly_id: string
  kind: string
  relative_hour_bucket: number
  transactions: number
  amount_usd: number
  amount_currency: string
  live_score: number
  signals: string[]
}

export type RealAnomalyList = {
  world: string
  dataset: string
  count: number
  anomalies: RealAnomaly[]
}

export type RealInvestigation = {
  provider: string
  provider_label: string
  headline: string
  summary: string
  signals: string[]
  limitations: string[]
  llm_used: boolean
}

export type RecentWorldStatus = {
  world: string
  dataset: string
  raw_csv_present: boolean
  artifacts: Record<string, boolean>
  ready: boolean
  amount_currency: string
}

export type RecentAnomaly = {
  anomaly_id: string
  kind: string
  kinds?: string[]
  hour_start: string
  transactions: number
  amount_usd: number
  amount_currency: string
  live_score: number
  signals: string[]
  evaluation_overlay?: {
    label?: string
    fraud_count?: number | null
    fraud_amount_usd?: number | null
    fraud_rate?: number | null
  } | null
}

export type RecentAnomalyList = {
  world: string
  dataset: string
  count: number
  anomalies: RecentAnomaly[]
}
