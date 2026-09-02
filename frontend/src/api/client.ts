import type {
  ActionState,
  ActionProposal,
  Approval,
  AuditList,
  ExecutionResult,
  HealthResponse,
  InvestigationAgentResult,
  InvestigationIntelligence,
  InvestigationProvider,
  InvestigationReport,
  InvestigationResponse,
  Spike,
  SpikeList,
  RealAnomalyList,
  RealInvestigation,
  RealWorldStatus,
  RecentAnomalyList,
  RecentWorldStatus,
} from './types'

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export function getApiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL
  return (configured ?? 'http://localhost:8000').replace(/\/$/, '')
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  })

  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
      else if (body.detail != null) detail = JSON.stringify(body.detail)
    } catch {
      // Keep the status fallback when the body is not JSON.
    }
    throw new ApiError(detail, response.status)
  }

  return (await response.json()) as T
}

export async function checkApiHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>('/api/health', { signal })
}

export async function listSpikes(signal?: AbortSignal): Promise<SpikeList> {
  return request<SpikeList>('/api/spikes', { signal })
}

export async function getSpike(spikeId: string, signal?: AbortSignal): Promise<Spike> {
  return request<Spike>(`/api/spikes/${encodeURIComponent(spikeId)}`, { signal })
}

export async function getInvestigation(
  spikeId: string,
  provider: InvestigationProvider = 'deterministic',
  signal?: AbortSignal,
): Promise<InvestigationResponse> {
  const query = new URLSearchParams({ provider })
  return request<InvestigationResponse>(
    `/api/spikes/${encodeURIComponent(spikeId)}/investigation?${query}`,
    { signal },
  )
}

export async function proposeAction(
  report: InvestigationReport,
  signal?: AbortSignal,
): Promise<ActionProposal> {
  return request<ActionProposal>('/api/actions/propose', {
    method: 'POST',
    body: JSON.stringify(report),
    signal,
  })
}

export async function approveAction(
  actionId: string,
  body: { approved_by: string; note?: string },
  signal?: AbortSignal,
): Promise<Approval> {
  return request<Approval>(`/api/actions/${encodeURIComponent(actionId)}/approve`, {
    method: 'POST',
    body: JSON.stringify({
      approved_by: body.approved_by,
      note: body.note ?? '',
    }),
    signal,
  })
}

export async function executeAction(
  actionId: string,
  signal?: AbortSignal,
): Promise<ExecutionResult> {
  return request<ExecutionResult>(`/api/actions/${encodeURIComponent(actionId)}/execute`, {
    method: 'POST',
    signal,
  })
}

export async function getAction(
  actionId: string,
  signal?: AbortSignal,
): Promise<ActionState> {
  return request<ActionState>(`/api/actions/${encodeURIComponent(actionId)}`, { signal })
}

export async function getRealStatus(signal?: AbortSignal): Promise<RealWorldStatus> {
  return request<RealWorldStatus>('/api/real/status', { signal })
}

export async function getRealProfile(signal?: AbortSignal): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('/api/real/profile', { signal })
}

export async function getRealBenchmark(signal?: AbortSignal): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('/api/real/benchmark', { signal })
}

export async function listRealAnomalies(signal?: AbortSignal): Promise<RealAnomalyList> {
  return request<RealAnomalyList>('/api/real/anomalies', { signal })
}

export async function getRealEvaluation(signal?: AbortSignal): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('/api/real/evaluation', { signal })
}

export async function getRealAnomaly(
  anomalyId: string,
  signal?: AbortSignal,
): Promise<{
  anomaly: Record<string, unknown>
  evidence: Record<string, unknown>
  investigation_state?: Record<string, unknown>
  investigation_intelligence?: InvestigationIntelligence | null
  investigation_agent?: InvestigationAgentResult | null
}> {
  return request(`/api/real/anomalies/${encodeURIComponent(anomalyId)}`, { signal })
}

export async function getRealModelEvaluation(
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('/api/real/model/evaluation', { signal })
}

export async function getRealInvestigation(
  anomalyId: string,
  provider = 'auto',
  signal?: AbortSignal,
): Promise<RealInvestigation> {
  const query = new URLSearchParams({ provider })
  return request(
    `/api/real/anomalies/${encodeURIComponent(anomalyId)}/investigation?${query}`,
    { signal },
  )
}

export async function proposeRealAction(
  anomalyId: string,
  provider = 'auto',
): Promise<Record<string, unknown>> {
  return request('/api/real/actions/propose', {
    method: 'POST',
    body: JSON.stringify({ anomaly_id: anomalyId, provider }),
  })
}

export async function approveRealAction(
  actionId: string,
  approvedBy: string,
): Promise<Record<string, unknown>> {
  return request(`/api/real/actions/${encodeURIComponent(actionId)}/approve`, {
    method: 'POST',
    body: JSON.stringify({ approved_by: approvedBy }),
  })
}

export async function simulateRealAction(actionId: string): Promise<Record<string, unknown>> {
  return request(`/api/real/actions/${encodeURIComponent(actionId)}/simulate`, {
    method: 'POST',
  })
}

export async function getRealAudit(
  anomalyId: string,
  signal?: AbortSignal,
): Promise<{ events: Record<string, unknown>[]; count: number }> {
  const query = new URLSearchParams({ anomaly_id: anomalyId })
  return request(`/api/real/audit?${query}`, { signal })
}

export async function getRecentStatus(signal?: AbortSignal): Promise<RecentWorldStatus> {
  return request<RecentWorldStatus>('/api/recent/status', { signal })
}

export async function getRecentProfile(signal?: AbortSignal): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('/api/recent/profile', { signal })
}

export async function getRecentBenchmark(signal?: AbortSignal): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('/api/recent/benchmark', { signal })
}

export async function listRecentAnomalies(signal?: AbortSignal): Promise<RecentAnomalyList> {
  return request<RecentAnomalyList>('/api/recent/anomalies', { signal })
}

export async function getRecentAnomaly(
  anomalyId: string,
  signal?: AbortSignal,
): Promise<{
  anomaly: Record<string, unknown>
  evidence: Record<string, unknown>
  investigation_state?: Record<string, unknown>
  investigation_intelligence?: InvestigationIntelligence | null
  investigation_agent?: InvestigationAgentResult | null
}> {
  return request(`/api/recent/anomalies/${encodeURIComponent(anomalyId)}`, { signal })
}

export async function getRecentEvaluation(signal?: AbortSignal): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('/api/recent/evaluation', { signal })
}

export async function getRecentInvestigation(
  anomalyId: string,
  provider = 'auto',
  signal?: AbortSignal,
): Promise<RealInvestigation> {
  const query = new URLSearchParams({ provider })
  return request(
    `/api/recent/anomalies/${encodeURIComponent(anomalyId)}/investigation?${query}`,
    { signal },
  )
}

export async function proposeRecentAction(
  anomalyId: string,
  provider = 'auto',
): Promise<Record<string, unknown>> {
  return request('/api/recent/actions/propose', {
    method: 'POST',
    body: JSON.stringify({ anomaly_id: anomalyId, provider }),
  })
}

export async function approveRecentAction(
  actionId: string,
  approvedBy: string,
): Promise<Record<string, unknown>> {
  return request(`/api/recent/actions/${encodeURIComponent(actionId)}/approve`, {
    method: 'POST',
    body: JSON.stringify({ approved_by: approvedBy }),
  })
}

export async function simulateRecentAction(actionId: string): Promise<Record<string, unknown>> {
  return request(`/api/recent/actions/${encodeURIComponent(actionId)}/simulate`, {
    method: 'POST',
  })
}

export async function getRecentAudit(
  anomalyId: string,
  signal?: AbortSignal,
): Promise<{ events: Record<string, unknown>[]; count: number }> {
  const query = new URLSearchParams({ anomaly_id: anomalyId })
  return request(`/api/recent/audit?${query}`, { signal })
}

export async function getCustomStatus(signal?: AbortSignal): Promise<Record<string, unknown>> {
  return request('/api/custom/status', { signal })
}

export function uploadCustomCsv(
  file: File,
  onProgress?: (sent: number, total: number) => void,
): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${getApiBaseUrl()}/api/custom/upload`)
    xhr.setRequestHeader('Accept', 'application/json')
    xhr.setRequestHeader('X-Filename', file.name)
    xhr.upload.onprogress = (event) => {
      if (onProgress && event.lengthComputable) onProgress(event.loaded, event.total)
    }
    xhr.onload = () => {
      let payload: { detail?: unknown } = {}
      try {
        payload = JSON.parse(xhr.responseText) as { detail?: unknown }
      } catch {
        payload = {}
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(payload as Record<string, unknown>)
        return
      }
      const detail =
        typeof payload.detail === 'string'
          ? payload.detail
          : payload.detail != null
            ? JSON.stringify(payload.detail)
            : `HTTP ${xhr.status}`
      reject(new ApiError(detail, xhr.status))
    }
    xhr.onerror = () => reject(new ApiError('Upload failed before the API responded.', 0))
    xhr.send(file)
  })
}

export async function getCustomSession(
  sessionId: string,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  return request(`/api/custom/sessions/${encodeURIComponent(sessionId)}`, { signal })
}

export async function confirmCustomMapping(
  sessionId: string,
  mapping: Record<string, string | null>,
): Promise<Record<string, unknown>> {
  return request(`/api/custom/sessions/${encodeURIComponent(sessionId)}/mapping`, {
    method: 'POST',
    body: JSON.stringify({ mapping }),
  })
}

export async function analyzeCustomSession(sessionId: string): Promise<Record<string, unknown>> {
  return request(`/api/custom/sessions/${encodeURIComponent(sessionId)}/analyze`, {
    method: 'POST',
  })
}

export async function getCustomAnomaly(
  sessionId: string,
  anomalyId: string,
  signal?: AbortSignal,
): Promise<{
  anomaly: Record<string, unknown>
  evidence: Record<string, unknown>
  investigation_state?: Record<string, unknown>
  investigation_intelligence?: InvestigationIntelligence | null
  investigation_agent?: InvestigationAgentResult | null
  session_id?: string
}> {
  return request(
    `/api/custom/sessions/${encodeURIComponent(sessionId)}/anomalies/${encodeURIComponent(anomalyId)}`,
    { signal },
  )
}

export async function getCustomInvestigation(
  sessionId: string,
  anomalyId: string,
  provider = 'auto',
  signal?: AbortSignal,
): Promise<RealInvestigation> {
  const query = new URLSearchParams({ provider })
  return request(
    `/api/custom/sessions/${encodeURIComponent(sessionId)}/anomalies/${encodeURIComponent(anomalyId)}/investigation?${query}`,
    { signal },
  )
}

export async function proposeCustomAction(
  sessionId: string,
  anomalyId: string,
  provider = 'auto',
): Promise<Record<string, unknown>> {
  return request(`/api/custom/sessions/${encodeURIComponent(sessionId)}/actions/propose`, {
    method: 'POST',
    body: JSON.stringify({ anomaly_id: anomalyId, provider }),
  })
}

export async function approveCustomAction(
  sessionId: string,
  actionId: string,
  approvedBy: string,
): Promise<Record<string, unknown>> {
  return request(
    `/api/custom/sessions/${encodeURIComponent(sessionId)}/actions/${encodeURIComponent(actionId)}/approve`,
    {
      method: 'POST',
      body: JSON.stringify({ approved_by: approvedBy }),
    },
  )
}

export async function simulateCustomAction(
  sessionId: string,
  actionId: string,
): Promise<Record<string, unknown>> {
  return request(
    `/api/custom/sessions/${encodeURIComponent(sessionId)}/actions/${encodeURIComponent(actionId)}/simulate`,
    { method: 'POST' },
  )
}

export async function getCustomAction(
  sessionId: string,
  actionId: string,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  return request(
    `/api/custom/sessions/${encodeURIComponent(sessionId)}/actions/${encodeURIComponent(actionId)}`,
    { signal },
  )
}

export async function getCustomAudit(
  sessionId: string,
  anomalyId: string,
  signal?: AbortSignal,
): Promise<{ events: Record<string, unknown>[]; count: number }> {
  const query = new URLSearchParams({ anomaly_id: anomalyId })
  return request(
    `/api/custom/sessions/${encodeURIComponent(sessionId)}/audit?${query}`,
    { signal },
  )
}

export async function listAudit(
  filters: { spike_id?: string; action_id?: string } = {},
  signal?: AbortSignal,
): Promise<AuditList> {
  const query = new URLSearchParams()
  if (filters.spike_id) query.set('spike_id', filters.spike_id)
  if (filters.action_id) query.set('action_id', filters.action_id)
  const suffix = query.toString() ? `?${query}` : ''
  return request<AuditList>(`/api/audit${suffix}`, { signal })
}
