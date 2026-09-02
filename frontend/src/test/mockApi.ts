import { vi } from 'vitest'
import type { ActionState } from '../api/types'
import {
  actionState,
  approval,
  coordInvestigation,
  coordSpike,
  emptyAudit,
  execution,
  festInvestigation,
  festSpike,
  proposal,
  sampleAgent,
  sampleIntelligence,
  spikeList,
} from './fixtures'

function analyzedCustomSession() {
  return {
    world: 'BRING YOUR DATA',
    session_id: 'cxs-mock',
    filename: 'merchant.csv',
    inspection: {
      rows: 116,
      column_count: 3,
      columns: ['transaction_id', 'amount', 'timestamp'],
    },
    mapping: { transaction_id: 'transaction_id', amount: 'amount', timestamp: 'timestamp' },
    mapping_proposals: [],
    mapping_summary: { identified_count: 3, identification_total: 5, headline: '3/5 required fields identified automatically.' },
    mapping_validation: { ready: true, missing: [] },
    compatibility: { status: 'partial' },
    summary: { transactions_analyzed: 116, temporal_anomalies: 1, amount_concentration_anomalies: 1 },
    evaluation: { available: false },
    anomalies: [
      {
        anomaly_id: 'cda-a',
        kind: 'Amount-concentration anomaly',
        time_display: '10 Jan 2026 · 7:00 PM',
        transactions: 76,
        amount: 58325.33,
        investigation: investigationFor('cda-a').status,
      },
      {
        anomaly_id: 'cda-b',
        kind: 'Temporal anomaly',
        time_display: '11 Jan 2026 · 3:00 PM',
        transactions: 40,
        amount: 12000,
        investigation: investigationFor('cda-b').status,
      },
    ],
  }
}

function customAnomalyDetail(id: string, kind: string, transactions: number, amount: number) {
  return {
    anomaly: { anomaly_id: id, kind, transactions, amount, hour_start: '2026-01-10T13:30:00' },
    evidence: {
      live_evidence: {
        transaction_count: { value: transactions },
        amount: { value: amount },
        temporal_window: { value: '2026-01-10T13:30:00' },
      },
      evaluation_overlay: {
        label: 'USER-PROVIDED GROUND TRUTH',
        fraud_count: 1,
        fraud_rate: 0.0132,
        used_as_detector_input: false,
        used_as_model_feature: false,
        note: 'USER-PROVIDED GROUND TRUTH is evaluation only. It is not a model feature and not the system\'s fraud decision.',
      },
      model_prediction: {},
      classifier: {
        status: 'scored',
        fraud_risk_score: 0.31,
        classification: 'Low risk',
        model: 'ieee_hgb',
        model_version: 2,
        feature_coverage: 0.008,
      },
    },
    investigation_state: investigationFor(id),
    investigation_intelligence: sampleIntelligence({
      world: 'BRING YOUR DATA',
      case_id: id,
      classifier_status: {
        status: 'LIMITED',
        headline: 'MODEL EVIDENCE: LIMITED',
        detail: 'The shared IEEE-CIS classifier was applied with low feature coverage.',
        not_fraud_confirmed: true,
      },
      entities: {
        available: false,
        missing: ['account_id', 'device_id', 'merchant'],
        note: 'This world does not contain identifiers that support entity clustering.',
      },
    }),
    investigation_agent: sampleAgent({
      world: 'BRING YOUR DATA',
      case_id: id,
      finding: 'This case was flagged by the world detector from live anomaly evidence.',
      contradictory_evidence: [
        {
          statement: 'This world does not contain identifiers that support entity clustering.',
          tool: 'inspect_entities',
          provenance: 'OBSERVED',
        },
      ],
      uncertainty: [
        'MODEL EVIDENCE: LIMITED — supporting evidence only. Not a fraud confirmation and not an action authorization.',
        'Unavailable identifiers: account_id, device_id, merchant.',
      ],
    }),
  }
}

type CustomInvestigation = {
  decision: Record<string, unknown> | null
  proposal: Record<string, unknown> | null
  approval: Record<string, unknown> | null
  execution: Record<string, unknown> | null
  audit: Record<string, unknown>[]
  status: Record<string, unknown>
}

function emptyInvestigation(): CustomInvestigation {
  return {
    decision: null,
    proposal: null,
    approval: null,
    execution: null,
    audit: [],
    status: {
      decision: 'not_recorded',
      approval: 'not_applicable',
      simulation: 'not_simulated',
      audit_count: 0,
    },
  }
}

function completedInvestigation(anomalyId: string, actionId: string): CustomInvestigation {
  const stamp = '2026-09-01T14:07:42+00:00'
  const audit = [
    { kind: 'CUSTOM_DECISION_RECORDED', timestamp: stamp, audit_event_id: 'e1', anomaly_id: anomalyId },
    { kind: 'CUSTOM_ACTION_PROPOSED', timestamp: stamp, audit_event_id: 'e2', anomaly_id: anomalyId, action_id: actionId },
    { kind: 'CUSTOM_ACTION_APPROVED', timestamp: stamp, audit_event_id: 'e3', anomaly_id: anomalyId, action_id: actionId },
    { kind: 'CUSTOM_ACTION_SIMULATED', timestamp: '2026-09-01T14:08:00+00:00', audit_event_id: 'e4', anomaly_id: anomalyId, action_id: actionId },
  ]
  return {
    decision: { anomaly_id: anomalyId, recorded_at: stamp, verdict: 'review_recommended' },
    proposal: { action_id: actionId, anomaly_id: anomalyId, action_type: 'flag_for_human_review', status: 'simulated', created_at: stamp },
    approval: { action_id: actionId, approved: true, approved_at: stamp },
    execution: {
      action_id: actionId,
      simulated: true,
      action_type: 'flag_for_human_review',
      razorpay_test: {
        status: 'unavailable',
        provider: 'razorpay',
        environment: 'test',
        message: 'Razorpay test integration is unavailable (configuration missing).',
      },
    },
    audit,
    status: { decision: 'recorded', approval: 'approved', simulation: 'completed', audit_count: 4 },
  }
}

type SyntheticInvestigation = {
  decision: Record<string, unknown> | null
  proposal: Record<string, unknown> | null
  approval: Record<string, unknown> | null
  execution: Record<string, unknown> | null
  audit: Record<string, unknown>[]
  status: Record<string, unknown>
}

const customInvestigations: Record<string, CustomInvestigation> = {}
const recentInvestigations: Record<string, CustomInvestigation> = {}
const syntheticInvestigations: Record<string, SyntheticInvestigation> = {}

function emptySyntheticInvestigation(): SyntheticInvestigation {
  return {
    decision: null,
    proposal: null,
    approval: null,
    execution: null,
    audit: [],
    status: {
      decision: 'not_recorded',
      approval: 'not_applicable',
      simulation: 'not_simulated',
      audit_count: 0,
    },
  }
}

function syntheticFor(spikeId: string): SyntheticInvestigation {
  if (!syntheticInvestigations[spikeId]) {
    syntheticInvestigations[spikeId] = emptySyntheticInvestigation()
  }
  return syntheticInvestigations[spikeId]
}

function refreshSyntheticStatus(item: SyntheticInvestigation) {
  item.status = {
    decision: item.decision || item.proposal ? 'recorded' : 'not_recorded',
    approval: item.approval?.approved === true ? 'approved' : item.proposal ? 'pending' : 'not_applicable',
    simulation: item.execution?.simulated === true ? 'completed' : 'not_simulated',
    audit_count: item.audit.length,
  }
}

export function resetSyntheticInvestigations() {
  for (const key of Object.keys(syntheticInvestigations)) {
    delete syntheticInvestigations[key]
  }
}

function recentInvestigationFor(anomalyId: string): CustomInvestigation {
  return recentInvestigations[anomalyId] ?? emptyInvestigation()
}

function seedCompletedA() {
  customInvestigations['cda-a'] = completedInvestigation('cda-a', 'cact-a')
  customInvestigations['cda-b'] = emptyInvestigation()
}

export function seedEmptyCustomInvestigations() {
  customInvestigations['cda-a'] = emptyInvestigation()
  customInvestigations['cda-b'] = emptyInvestigation()
}

function investigationFor(anomalyId: string): CustomInvestigation {
  return customInvestigations[anomalyId] ?? emptyInvestigation()
}

function readJsonBody(init?: RequestInit): Record<string, unknown> {
  if (!init?.body || typeof init.body !== 'string') return {}
  try {
    return JSON.parse(init.body) as Record<string, unknown>
  } catch {
    return {}
  }
}

function refreshInvestigationStatus(item: CustomInvestigation) {
  item.status = {
    decision: item.decision ? 'recorded' : 'not_recorded',
    approval: item.approval?.approved === true ? 'approved' : item.proposal ? 'pending' : 'not_applicable',
    simulation: item.execution?.simulated === true ? 'completed' : 'not_simulated',
    audit_count: item.audit.length,
  }
}

export function jsonResponse(data: unknown, status = 200): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(data), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

export function defaultApiResponse(
  input: RequestInfo | URL,
  init?: RequestInit,
  state: ActionState = actionState(),
): Promise<Response> {
  const url = new URL(String(input))
  const method = (init?.method ?? 'GET').toUpperCase()
  const path = url.pathname

  if (path === '/api/health' && method === 'GET') {
    return jsonResponse({
      status: 'ok',
      service: 'fraud-spike-investigator',
      component: 'backend',
    })
  }
  if (path === '/api/spikes' && method === 'GET') return jsonResponse(spikeList)
  if (path === `/api/spikes/${coordSpike.spike_id}` && method === 'GET') {
    return jsonResponse(coordSpike)
  }
  if (path === `/api/spikes/${festSpike.spike_id}` && method === 'GET') {
    return jsonResponse(festSpike)
  }
  if (path === `/api/spikes/${coordSpike.spike_id}/investigation` && method === 'GET') {
    return jsonResponse({
      ...coordInvestigation,
      investigation_state: syntheticInvestigations[coordSpike.spike_id] ?? emptySyntheticInvestigation(),
    })
  }
  if (path === `/api/spikes/${festSpike.spike_id}/investigation` && method === 'GET') {
    return jsonResponse({
      ...festInvestigation,
      investigation_state: syntheticInvestigations[festSpike.spike_id] ?? emptySyntheticInvestigation(),
    })
  }
  if (path === '/api/actions/propose' && method === 'POST') {
    const body = readJsonBody(init)
    const spikeId = typeof body.spike_id === 'string' ? body.spike_id : coordSpike.spike_id
    const current = syntheticFor(spikeId)
    if (current.proposal && typeof current.proposal.action_id === 'string') {
      return jsonResponse(current.proposal)
    }
    const created =
      spikeId === festSpike.spike_id
        ? {
            ...proposal,
            action_id: 'act-fest',
            spike_id: festSpike.spike_id,
            action_type: 'monitor',
            verdict: 'likely_festive',
            scope: 'window-level volume only; no entity block',
          }
        : { ...proposal, spike_id: spikeId }
    current.proposal = created
    current.decision = {
      spike_id: spikeId,
      recorded_at: created.created_at,
      verdict: created.verdict,
      action_type: created.action_type,
    }
    current.audit = [
      ...current.audit,
      {
        event_id: `${created.action_id}-decision`,
        event_type: 'DECISION_RECORDED',
        timestamp: created.created_at,
        action_id: created.action_id,
        spike_id: spikeId,
        actor: 'system',
        details: { decision_representation: 'proposal_read_model' },
      },
      {
        event_id: `${created.action_id}-proposed`,
        event_type: 'ACTION_PROPOSED',
        timestamp: created.created_at,
        action_id: created.action_id,
        spike_id: spikeId,
        actor: 'system',
        details: {},
      },
    ]
    refreshSyntheticStatus(current)
    return jsonResponse(created)
  }
  if (path.endsWith('/approve') && path.includes('/api/actions/') && method === 'POST') {
    const actionId = path.split('/actions/')[1]?.split('/')[0] ?? proposal.action_id
    const spikeId =
      actionId === 'act-fest' ? festSpike.spike_id : coordSpike.spike_id
    const current = syntheticFor(spikeId)
    const recorded = { ...approval, action_id: actionId }
    current.approval = recorded
    if (current.proposal) current.proposal = { ...current.proposal, status: 'approved' }
    if (!current.audit.some((event) => event.event_type === 'ACTION_APPROVED')) {
      current.audit = [
        ...current.audit,
        {
          event_id: `${actionId}-approved`,
          event_type: 'ACTION_APPROVED',
          timestamp: approval.approved_at,
          action_id: actionId,
          spike_id: spikeId,
          actor: 'analyst',
          details: {},
        },
      ]
    }
    refreshSyntheticStatus(current)
    return jsonResponse(recorded)
  }
  if (path.endsWith('/execute') && path.includes('/api/actions/') && method === 'POST') {
    const actionId = path.split('/actions/')[1]?.split('/')[0] ?? proposal.action_id
    const spikeId =
      actionId === 'act-fest' ? festSpike.spike_id : coordSpike.spike_id
    const current = syntheticFor(spikeId)
    const recorded = { ...execution, action_id: actionId }
    current.execution = recorded
    if (current.proposal) current.proposal = { ...current.proposal, status: 'simulated' }
    if (!current.audit.some((event) => event.event_type === 'ACTION_SIMULATED')) {
      current.audit = [
        ...current.audit,
        {
          event_id: `${actionId}-simulated`,
          event_type: 'ACTION_SIMULATED',
          timestamp: '2026-01-18T03:07:00Z',
          action_id: actionId,
          spike_id: spikeId,
          actor: 'simulator',
          details: {},
        },
        {
          event_id: `${actionId}-verified`,
          event_type: 'ACTION_VERIFIED',
          timestamp: '2026-01-18T03:07:00Z',
          action_id: actionId,
          spike_id: spikeId,
          actor: 'verifier',
          details: {},
        },
      ]
    }
    refreshSyntheticStatus(current)
    return jsonResponse(recorded)
  }
  if (path.startsWith('/api/actions/') && method === 'GET') {
    const actionId = path.split('/actions/')[1] ?? ''
    for (const item of Object.values(syntheticInvestigations)) {
      if (item.proposal && item.proposal.action_id === actionId) {
        return jsonResponse({
          proposal: item.proposal,
          approval: item.approval,
          execution: item.execution,
          verification: item.execution && typeof item.execution === 'object' && 'verification' in item.execution
            ? item.execution.verification
            : null,
        })
      }
    }
    return jsonResponse(state)
  }
  if (path === '/api/audit' && method === 'GET') {
    const spikeId = url.searchParams.get('spike_id')
    const actionId = url.searchParams.get('action_id')
    let events = Object.values(syntheticInvestigations).flatMap((item) => item.audit)
    if (spikeId) events = events.filter((event) => event.spike_id === spikeId)
    if (actionId) events = events.filter((event) => event.action_id === actionId)
    return jsonResponse({ events, count: events.length })
  }
  if (path === '/api/real/status' && method === 'GET') {
    return jsonResponse({
      world: 'REAL PUBLIC DATA',
      dataset: 'IEEE-CIS Fraud Detection',
      raw_train_present: true,
      artifacts: { profile: true, benchmark: true, anomalies: true },
      ready: true,
      amount_currency: 'USD',
    })
  }
  if (path === '/api/real/profile' && method === 'GET') {
    return jsonResponse({
      world: 'REAL PUBLIC DATA',
      dataset: 'IEEE-CIS Fraud Detection',
      amount_currency: 'USD',
      identity_coverage: { coverage: 0.24 },
      train_labelled: { transactions: 3, fraud_count: 1, fraud_rate: 0.33 },
    })
  }
  if (path === '/api/real/benchmark' && method === 'GET') {
    return jsonResponse({
      amount_currency: 'USD',
      measurements: {
        total_transactions: { value: 3 },
        labelled_fraud_transactions: { value: 1 },
        fraud_transaction_rate: { value: 0.33 },
        total_amount_usd: { value: 39.5 },
        labelled_fraud_amount_usd: { value: 25.5 },
      },
      by_product: [{ value: 'W', labelled_fraud_rate: 0.1 }],
    })
  }
  if (path === '/api/real/anomalies' && method === 'GET') {
    return jsonResponse({
      world: 'REAL PUBLIC DATA',
      dataset: 'IEEE-CIS Fraud Detection',
      count: 1,
      anomalies: [
        {
          anomaly_id: 'rda-24',
          kind: 'REAL DATA ANOMALY',
          relative_hour_bucket: 24,
          transactions: 3,
          amount_usd: 39.5,
          amount_currency: 'USD',
          live_score: 2.1,
          signals: ['elevated transaction volume'],
        },
      ],
    })
  }
  if (path === '/api/real/anomalies/rda-24' && method === 'GET') {
    return jsonResponse({
      anomaly: { anomaly_id: 'rda-24', relative_hour_bucket: 24 },
      evidence: {
        live_evidence: {
          transaction_count: { value: 3 },
          amount_usd: { value: 39.5 },
          identity_coverage: { value: 0.3 },
          product_concentration: { value: { value: 'W', share: 0.9 } },
          card_proxy_concentration: { value: { value: 'visa' } },
          address_proxy_concentration: { value: { value: '87' } },
          device_proxy: { value: { value: 'mobile' } },
        },
        evaluation_overlay: { fraud_rate: 0.33 },
        classifier: {
          status: 'scored',
          fraud_risk_score: 0.72,
          classification: 'High risk',
          model: 'ieee_hgb',
          model_version: 2,
          feature_coverage: 1,
        },
        model_prediction: {
          label: 'MODEL PREDICTION',
          sample_scope: 'IN_SAMPLE_MODEL_OVERLAY',
          high_risk_count: 1,
          p95_score: 0.72,
          threshold: 0.1,
          top_transactions: [
            {
              transaction_id: '24',
              fraud_risk_score: 0.81,
              provenance: 'MODEL PREDICTION',
              delayed_ground_truth: 0,
            },
          ],
        },
      },
      investigation_intelligence: sampleIntelligence({
        world: 'REAL PUBLIC DATA',
        case_id: 'rda-24',
        classifier_status: {
          status: 'CONTEXTUAL',
          headline: 'MODEL EVIDENCE: CONTEXTUAL',
          detail:
            'IN_SAMPLE_MODEL_OVERLAY — supporting evidence for this investigation, not held-out test performance.',
          not_fraud_confirmed: true,
          sample_scope: 'IN_SAMPLE_MODEL_OVERLAY',
        },
        entities: {
          available: true,
          groups: {
            product: [{ id: 'W', share: 0.9, count: 3, provenance: 'DERIVED' }],
          },
          missing: ['IP/subnet', 'true account identity'],
          note: 'ProductCD share is derived. card4 is a proxy, not a true card identity.',
        },
      }),
      investigation_agent: sampleAgent({
        world: 'REAL PUBLIC DATA',
        case_id: 'rda-24',
        finding: 'IEEE anomaly at the selected relative hour.',
        uncertainty: [
          'MODEL EVIDENCE: CONTEXTUAL — supporting evidence only. Not a fraud confirmation and not an action authorization.',
        ],
      }),
    })
  }
  if (path === '/api/real/evaluation' && method === 'GET') {
    return jsonResponse({
      world: 'REAL PUBLIC DATA',
      temporal_holdout: { precision: 0, recall: 0, counts: { tp: 0, fp: 235, fn: 0 } },
    })
  }
  if (path === '/api/real/model/evaluation' && method === 'GET') {
    return jsonResponse({
      world: 'REAL PUBLIC DATA',
      provenance: 'MODEL PREDICTION',
      ranking: { pr_auc: 0.42, roc_auc: 0.88 },
      operating_point: {
        threshold: 0.1,
        f1: 0.31,
        precision: 0.18,
        recall: 0.74,
        confusion: { tp: 10, fp: 40, tn: 100, fn: 5 },
      },
    })
  }
  if (path === '/api/real/anomalies/rda-24/investigation' && method === 'GET') {
    return jsonResponse({
      provider: 'deterministic',
      provider_label: 'DETERMINISTIC',
      headline: 'REAL DATA ANOMALY',
      summary: 'Relative hour bucket 24 is a REAL DATA ANOMALY.',
      signals: ['elevated transaction volume'],
      limitations: ['IP address and subnet are unavailable.'],
      llm_used: false,
    })
  }
  if (path === '/api/real/actions/propose' && method === 'POST') {
    return jsonResponse({
      action_id: 'ract-mock',
      anomaly_id: 'rda-24',
      action_type: 'flag_high_risk_transactions',
      simulation_only: true,
    })
  }
  if (path === '/api/real/actions/ract-mock/approve' && method === 'POST') {
    return jsonResponse({ action_id: 'ract-mock', approved: true, approved_by: 'analyst' })
  }
  if (path === '/api/real/actions/ract-mock/simulate' && method === 'POST') {
    return jsonResponse({
      action_id: 'ract-mock',
      simulated: true,
      result:
        'Simulated flag_high_risk_transactions. Razorpay test integration is unavailable (configuration missing).',
      razorpay_test: {
        status: 'unavailable',
        provider: 'razorpay',
        environment: 'test',
        message: 'Razorpay test integration is unavailable (configuration missing).',
      },
    })
  }
  if (path === '/api/real/audit' && method === 'GET') {
    return jsonResponse({ world: 'REAL PUBLIC DATA', count: 0, events: [] })
  }
  if (path === '/api/recent/status' && method === 'GET') {
    return jsonResponse({
      world: 'RECENT PUBLIC DATA',
      dataset: '2026 ONLINE BANKING FRAUD DATA',
      raw_csv_present: true,
      artifacts: { profile: true, benchmark: true, anomalies: true, evaluation: true },
      ready: true,
      amount_currency: 'USD',
    })
  }
  if (path === '/api/recent/profile' && method === 'GET') {
    return jsonResponse({
      world: 'RECENT PUBLIC DATA',
      dataset: '2026 ONLINE BANKING FRAUD DATA',
      amount_currency: 'USD',
      january_collection: { rows: 56962, fraud_count: 98, fraud_rate: 0.00172 },
    })
  }
  if (path === '/api/recent/benchmark' && method === 'GET') {
    return jsonResponse({
      world: 'RECENT PUBLIC DATA',
      dataset: '2026 ONLINE BANKING FRAUD DATA',
      amount_currency: 'USD',
      measurements: {
        total_transactions: { value: 56962 },
        labelled_fraud_transactions: { value: 98 },
        fraud_transaction_rate: { value: 0.001720445 },
        total_amount_usd: { value: 12107485.97 },
        labelled_fraud_amount_usd: { value: 42100.0 },
      },
    })
  }
  if (path === '/api/recent/anomalies' && method === 'GET') {
    return jsonResponse({
      world: 'RECENT PUBLIC DATA',
      dataset: '2026 ONLINE BANKING FRAUD DATA',
      count: 2,
      anomalies: [
        {
          anomaly_id: 'rct-20260104-20',
          kind: 'Amount concentration',
          hour_start: '2026-01-04T20:00:00',
          transactions: 70,
          amount_usd: 157784.18,
          amount_currency: 'USD',
          live_score: 8.2,
          signals: ['elevated transaction amount'],
        },
        {
          anomaly_id: 'rct-20260115-14',
          kind: 'Temporal anomaly',
          hour_start: '2026-01-15T14:00:00',
          transactions: 240,
          amount_usd: 98000,
          amount_currency: 'USD',
          live_score: 3.1,
          signals: ['elevated transaction volume'],
          evaluation_overlay: {
            label: 'DELAYED GROUND TRUTH',
            fraud_count: 2,
            fraud_rate: 0.0083,
            fraud_amount_usd: 410,
          },
        },
      ],
    })
  }
  if (path.startsWith('/api/recent/anomalies/') && path.endsWith('/investigation') && method === 'GET') {
    return jsonResponse({
      provider: 'deterministic',
      provider_label: 'DETERMINISTIC',
      headline: 'Temporal anomaly',
      summary: 'January 2026 window. Detection used hour-level volume and amount only.',
      signals: ['elevated transaction amount'],
      limitations: ['Classifier output is independent of deterministic detection and is not a live decision.'],
      llm_used: false,
    })
  }
  if (path.startsWith('/api/recent/anomalies/') && method === 'GET') {
    const anomalyId = path.split('/api/recent/anomalies/')[1] ?? ''
    const amount = anomalyId === 'rct-20260104-20' ? 157784.18 : 98000
    const txs = anomalyId === 'rct-20260104-20' ? 70 : 240
    const kind = anomalyId === 'rct-20260104-20' ? 'Amount concentration' : 'Temporal anomaly'
    const hour = anomalyId === 'rct-20260104-20' ? '2026-01-04T20:00:00' : '2026-01-15T14:00:00'
    return jsonResponse({
      anomaly: { anomaly_id: anomalyId, kind, hour_start: hour, transactions: txs, amount_usd: amount },
      evidence: {
        anomaly_id: anomalyId,
        live_evidence: {
          transaction_count: { value: txs, label: 'OBSERVED' },
          amount_usd: { value: amount, label: 'OBSERVED' },
          temporal_window: { value: hour, label: 'DERIVED' },
        },
        evaluation_overlay: { label: 'DELAYED GROUND TRUTH', fraud_count: 2, fraud_rate: 0.0083 },
        source_dataset_model_output: { used: false },
        classifier: {
          status: 'scored',
          fraud_risk_score: 0.42,
          classification: 'Low risk',
          model: 'ieee_hgb',
          model_version: 2,
          feature_coverage: 0.005,
        },
      },
      investigation_state: recentInvestigationFor(anomalyId),
      investigation_intelligence: sampleIntelligence({
        world: 'RECENT PUBLIC DATA',
        case_id: anomalyId,
        classifier_status: {
          status: 'LIMITED',
          headline: 'MODEL EVIDENCE: LIMITED',
          detail: 'The shared IEEE-CIS classifier was applied with low feature coverage.',
          not_fraud_confirmed: true,
        },
        entities: {
          available: false,
          missing: ['account', 'device', 'merchant', 'SKU'],
          note: 'This world does not contain identifiers that support entity clustering.',
        },
        brief: {
          why_flagged: ['January anomaly at the selected hour.'],
          what_supports_risk: ['Transferred classifier with limited coverage. Not a January decision input.'],
          observed: [`${txs} transactions.`],
          derived: ['Hour bucket is floor(timestamp to hour).'],
          uncertain: ['Classifier coverage on January features is limited.'],
          next_checks: ['Do not treat the transferred High-risk label as fraud confirmed.'],
        },
      }),
      investigation_agent: sampleAgent({
        world: 'RECENT PUBLIC DATA',
        case_id: anomalyId,
        finding: 'January anomaly at the selected hour.',
        contradictory_evidence: [
          {
            statement: 'This world does not contain identifiers that support entity clustering.',
            tool: 'inspect_entities',
            provenance: 'OBSERVED',
          },
        ],
        uncertainty: [
          'MODEL EVIDENCE: LIMITED — supporting evidence only. Not a fraud confirmation and not an action authorization.',
          'Unavailable identifiers: account, device, merchant, SKU.',
        ],
      }),
    })
  }
  if (path === '/api/recent/actions/propose' && method === 'POST') {
    const anomalyId = String(readJsonBody(init).anomaly_id || 'rct-20260115-14')
    const current = recentInvestigationFor(anomalyId)
    if (current.proposal) return jsonResponse(current.proposal)
    const stamp = '2026-09-01T15:00:00+00:00'
    const actionId = `nact-${anomalyId}`
    current.decision = { anomaly_id: anomalyId, recorded_at: stamp, verdict: 'review_recommended' }
    current.proposal = {
      action_id: actionId,
      anomaly_id: anomalyId,
      action_type: 'flag_for_human_review',
      status: 'proposed',
      created_at: stamp,
    }
    current.audit = [
      { kind: 'RECENT_DECISION_RECORDED', timestamp: stamp, audit_event_id: `${anomalyId}-e1`, anomaly_id: anomalyId },
      { kind: 'RECENT_ACTION_PROPOSED', timestamp: stamp, audit_event_id: `${anomalyId}-e2`, anomaly_id: anomalyId, action_id: actionId },
    ]
    recentInvestigations[anomalyId] = current
    refreshInvestigationStatus(current)
    return jsonResponse(current.proposal)
  }
  if (path.endsWith('/approve') && path.includes('/api/recent/actions/') && method === 'POST') {
    const actionId = path.split('/actions/')[1]?.split('/')[0] ?? ''
    const anomalyId = actionId.replace(/^nact-/, '')
    const current = recentInvestigationFor(anomalyId)
    const stamp = '2026-09-01T15:00:00+00:00'
    current.approval = { action_id: actionId, approved: true, approved_at: stamp }
    if (current.proposal) current.proposal = { ...current.proposal, status: 'approved' }
    if (!current.audit.some((event) => event.kind === 'RECENT_ACTION_APPROVED')) {
      current.audit = [
        ...current.audit,
        { kind: 'RECENT_ACTION_APPROVED', timestamp: stamp, audit_event_id: `${anomalyId}-e3`, anomaly_id: anomalyId, action_id: actionId },
      ]
    }
    recentInvestigations[anomalyId] = current
    refreshInvestigationStatus(current)
    return jsonResponse(current.approval)
  }
  if (path.endsWith('/simulate') && path.includes('/api/recent/actions/') && method === 'POST') {
    const actionId = path.split('/actions/')[1]?.split('/')[0] ?? ''
    const anomalyId = actionId.replace(/^nact-/, '')
    const current = recentInvestigationFor(anomalyId)
    current.execution = {
      action_id: actionId,
      simulated: true,
      action_type: 'flag_for_human_review',
      razorpay_test: {
        status: 'unavailable',
        provider: 'razorpay',
        environment: 'test',
        message: 'Razorpay test integration is unavailable (configuration missing).',
      },
    }
    if (current.proposal) current.proposal = { ...current.proposal, status: 'simulated' }
    if (!current.audit.some((event) => event.kind === 'RECENT_ACTION_SIMULATED')) {
      current.audit = [
        ...current.audit,
        {
          kind: 'RECENT_ACTION_SIMULATED',
          timestamp: '2026-09-01T15:01:00+00:00',
          audit_event_id: `${anomalyId}-e4`,
          anomaly_id: anomalyId,
          action_id: actionId,
        },
      ]
    }
    recentInvestigations[anomalyId] = current
    refreshInvestigationStatus(current)
    return jsonResponse(current.execution)
  }
  if (path === '/api/recent/audit' && method === 'GET') {
    const anomalyId = url.searchParams.get('anomaly_id') ?? ''
    const events = recentInvestigationFor(anomalyId).audit
    return jsonResponse({ world: 'RECENT PUBLIC DATA', count: events.length, events })
  }
  if (path === '/api/custom/status' && method === 'GET') {
    return jsonResponse({
      world: 'BRING YOUR DATA',
      dataset: 'USER-PROVIDED DATA',
      active_sessions: 0,
      storage: 'isolated_temp_file',
      mixed_with_benchmarks: false,
      upload_limits: { max_bytes: 1073741824, max_mb: 1024, max_rows: 2000000 },
    })
  }
  if (path === '/api/custom/upload' && method === 'POST') {
    return jsonResponse({
      world: 'BRING YOUR DATA',
      session_id: 'cxs-mock',
      filename: 'upload.csv',
      inspection: {
        rows: 4,
        column_count: 3,
        columns: ['transaction_id', 'amount', 'timestamp'],
        amount_coverage: 1,
        timestamp_coverage: 1,
        duplicate_row_count: 0,
        fraud_label_available: false,
      },
      mapping_proposals: [
        {
          target: 'transaction_id',
          label: 'Transaction ID',
          suggested: 'transaction_id',
          ambiguous: false,
          confidence: 'high',
          auto_accepted: true,
        },
        {
          target: 'amount',
          label: 'Amount',
          suggested: 'amount',
          ambiguous: false,
          confidence: 'high',
          auto_accepted: true,
        },
        {
          target: 'timestamp',
          label: 'Timestamp',
          suggested: 'timestamp',
          ambiguous: false,
          confidence: 'high',
          auto_accepted: true,
        },
      ],
      mapping_summary: {
        identified_count: 3,
        identification_total: 5,
        headline: '3/5 required fields identified automatically.',
      },
      mapping_validation: { ready: true, missing: [] },
      privacy: { mixed_with_existing_datasets: false, labels_invented: false },
    })
  }
  if (path === '/api/custom/sessions/cxs-mock' && method === 'GET') {
    return jsonResponse(analyzedCustomSession())
  }
  if (path === '/api/custom/sessions/cxs-mock/anomalies/cda-a' && method === 'GET') {
    return jsonResponse(customAnomalyDetail('cda-a', 'Amount-concentration anomaly', 76, 58325.33))
  }
  if (path === '/api/custom/sessions/cxs-mock/anomalies/cda-b' && method === 'GET') {
    return jsonResponse(customAnomalyDetail('cda-b', 'Temporal anomaly', 40, 12000))
  }
  if (path.endsWith('/investigation') && path.includes('/api/custom/sessions/cxs-mock/') && method === 'GET') {
    return jsonResponse({
      provider: 'deterministic',
      provider_label: 'DETERMINISTIC',
      headline: 'Custom-data anomaly',
      summary: 'User-dataset window contains an independent concentration anomaly.',
      signals: ['elevated transaction amount'],
      limitations: [],
      llm_used: false,
    })
  }
  if (path === '/api/custom/sessions/cxs-mock/actions/propose' && method === 'POST') {
    const anomalyId = String(readJsonBody(init).anomaly_id || 'cda-a')
    const current = investigationFor(anomalyId)
    if (current.proposal) return jsonResponse(current.proposal)
    const stamp = '2026-09-01T14:07:42+00:00'
    const actionId = anomalyId === 'cda-b' ? 'cact-b' : 'cact-a'
    current.decision = { anomaly_id: anomalyId, recorded_at: stamp, verdict: 'review_recommended' }
    current.proposal = {
      action_id: actionId,
      anomaly_id: anomalyId,
      action_type: 'flag_for_human_review',
      status: 'proposed',
      created_at: stamp,
    }
    current.audit = [
      { kind: 'CUSTOM_DECISION_RECORDED', timestamp: stamp, audit_event_id: `${anomalyId}-e1`, anomaly_id: anomalyId },
      { kind: 'CUSTOM_ACTION_PROPOSED', timestamp: stamp, audit_event_id: `${anomalyId}-e2`, anomaly_id: anomalyId, action_id: actionId },
    ]
    customInvestigations[anomalyId] = current
    refreshInvestigationStatus(current)
    return jsonResponse(current.proposal)
  }
  if (path.endsWith('/approve') && path.includes('/api/custom/sessions/cxs-mock/actions/') && method === 'POST') {
    const actionId = path.split('/actions/')[1]?.split('/')[0] ?? 'cact-a'
    const anomalyId = actionId === 'cact-b' ? 'cda-b' : 'cda-a'
    const current = investigationFor(anomalyId)
    const stamp = '2026-09-01T14:07:42+00:00'
    current.approval = { action_id: actionId, approved: true, approved_at: stamp }
    if (current.proposal) current.proposal = { ...current.proposal, status: 'approved' }
    if (!current.audit.some((event) => event.kind === 'CUSTOM_ACTION_APPROVED')) {
      current.audit = [
        ...current.audit,
        { kind: 'CUSTOM_ACTION_APPROVED', timestamp: stamp, audit_event_id: `${anomalyId}-e3`, anomaly_id: anomalyId, action_id: actionId },
      ]
    }
    customInvestigations[anomalyId] = current
    refreshInvestigationStatus(current)
    return jsonResponse(current.approval)
  }
  if (path.endsWith('/simulate') && path.includes('/api/custom/sessions/cxs-mock/actions/') && method === 'POST') {
    const actionId = path.split('/actions/')[1]?.split('/')[0] ?? 'cact-a'
    const anomalyId = actionId === 'cact-b' ? 'cda-b' : 'cda-a'
    const current = investigationFor(anomalyId)
    current.execution = {
      action_id: actionId,
      simulated: true,
      action_type: 'flag_for_human_review',
      razorpay_test: {
        status: 'unavailable',
        provider: 'razorpay',
        environment: 'test',
        message: 'Razorpay test integration is unavailable (configuration missing).',
      },
    }
    if (current.proposal) current.proposal = { ...current.proposal, status: 'simulated' }
    if (!current.audit.some((event) => event.kind === 'CUSTOM_ACTION_SIMULATED')) {
      current.audit = [
        ...current.audit,
        {
          kind: 'CUSTOM_ACTION_SIMULATED',
          timestamp: '2026-09-01T14:08:00+00:00',
          audit_event_id: `${anomalyId}-e4`,
          anomaly_id: anomalyId,
          action_id: actionId,
        },
      ]
    }
    customInvestigations[anomalyId] = current
    refreshInvestigationStatus(current)
    return jsonResponse(current.execution)
  }
  if (path.includes('/api/custom/sessions/cxs-mock/actions/') && method === 'GET') {
    const actionId = path.split('/actions/')[1] ?? ''
    const anomalyId = actionId === 'cact-b' ? 'cda-b' : 'cda-a'
    const current = investigationFor(anomalyId)
    return jsonResponse({
      proposal: current.proposal,
      approval: current.approval,
      execution: current.execution,
      decision: current.decision,
    })
  }
  if (path === '/api/custom/sessions/cxs-mock/audit' && method === 'GET') {
    const anomalyId = url.searchParams.get('anomaly_id') ?? 'cda-a'
    const events = investigationFor(anomalyId).audit
    return jsonResponse({ count: events.length, events })
  }
  if (path === '/api/recent/evaluation' && method === 'GET') {
    return jsonResponse({
      world: 'RECENT PUBLIC DATA',
      dataset: '2026 ONLINE BANKING FRAUD DATA',
      methodology: {
        classifier_metrics_calculated: false,
        source_model_used_as_our_prediction: false,
        reason:
          'This adapter does not emit an independent fraud score that can be compared with is_fraud.',
      },
    })
  }
  return jsonResponse({ detail: `Unhandled ${method} ${path}` }, 404)
}

export function installApiMock() {
  resetSyntheticInvestigations()
  seedCompletedA()
  recentInvestigations['rct-20260104-20'] = emptyInvestigation()
  recentInvestigations['rct-20260115-14'] = emptyInvestigation()
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
    defaultApiResponse(input, init),
  )
  vi.stubGlobal('fetch', fetchMock)

  class MockXHR {
    status = 0
    responseText = ''
    upload = { onprogress: null }
    onload: (() => void) | null = null
    onerror: (() => void) | null = null
    private url = 'http://localhost:8000/api/custom/upload'

    open(_method: string, url: string) {
      this.url = url
    }

    setRequestHeader() {}

    send() {
      void defaultApiResponse(this.url, { method: 'POST' }).then(async (response) => {
        this.status = response.status
        this.responseText = await response.text()
        this.onload?.()
      })
    }
  }

  vi.stubGlobal('XMLHttpRequest', MockXHR as unknown as typeof XMLHttpRequest)
  return fetchMock
}
