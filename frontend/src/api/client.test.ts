import { afterEach, expect, test, vi } from 'vitest'
import { getApiBaseUrl, getInvestigation, listSpikes, proposeAction, uploadCustomCsv } from './client'

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

test('API client does not send an oversized governance ticket header', async () => {
  vi.stubEnv('VITE_API_BASE_URL', 'http://api.test:9000')
  sessionStorage.clear()
  sessionStorage.setItem('fsi.governanceTicket', `v1.${'x'.repeat(7000)}`)
  const fetchMock = vi.fn(() =>
    Promise.resolve(
      new Response(JSON.stringify({ spikes: [], count: 0 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
  vi.stubGlobal('fetch', fetchMock)
  await listSpikes()
  const headers = new Headers(fetchMock.mock.calls.at(0)?.[1]?.headers as HeadersInit)
  expect(headers.get('X-Governance-Ticket')).toBeNull()
})

test('API client sends and stores the governance ticket across requests', async () => {
  vi.stubEnv('VITE_API_BASE_URL', 'http://api.test:9000')
  sessionStorage.clear()
  const fetchMock = vi.fn(() =>
    Promise.resolve(
      new Response(JSON.stringify({ action_id: 'act-1', status: 'proposed' }), {
        status: 200,
        headers: {
          'Content-Type': 'application/json',
          'X-Governance-Ticket': 'v1.ticket-from-server',
        },
      }),
    ),
  )
  vi.stubGlobal('fetch', fetchMock)
  sessionStorage.setItem('fsi.governanceTicket', 'v1.ticket-from-client')
  await proposeAction({
    spike_id: 'spk-1',
    verdict: 'inconclusive',
    recommended_action: { type: 'review', scope: 'window', reason: 'n/a' },
    human_approval_required: true,
    summary: 'n/a',
    confidence: 0.4,
    supporting_evidence: [],
    contradicting_evidence: [],
    key_entities: [],
    reasoning: 'n/a',
    limitations: [],
    provider: 'deterministic_reasoner',
  } as never)
  const headers = new Headers(fetchMock.mock.calls.at(0)?.[1]?.headers as HeadersInit)
  expect(headers.get('X-Governance-Ticket')).toBe('v1.ticket-from-client')
  expect(sessionStorage.getItem('fsi.governanceTicket')).toBe('v1.ticket-from-server')
})

test('API client uses the configured base URL', async () => {
  vi.stubEnv('VITE_API_BASE_URL', 'http://api.test:9000')
  const fetchMock = vi.fn(() =>
    Promise.resolve(
      new Response(JSON.stringify({ spikes: [], count: 0 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
  vi.stubGlobal('fetch', fetchMock)

  expect(getApiBaseUrl()).toBe('http://api.test:9000')
  await listSpikes()
  const spikeCall = fetchMock.mock.calls.at(0)
  expect(spikeCall).toBeDefined()
  expect(String(spikeCall?.[0])).toBe('http://api.test:9000/api/spikes')
})

test('investigation requests the deterministic provider by default', async () => {
  vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:8000')
  const fetchMock = vi.fn(() =>
    Promise.resolve(
      new Response(
        JSON.stringify({
          provider: 'deterministic_reasoner',
          evidence_source: 'phase_2a_deterministic',
          report: {
            spike_id: 'spk-1',
            verdict: 'inconclusive',
            confidence: 0.4,
            summary: 'n/a',
            supporting_evidence: [],
            contradicting_evidence: [],
            key_entities: [],
            reasoning: 'n/a',
            recommended_action: { type: 'review', scope: 'window', reason: 'n/a' },
            human_approval_required: true,
            limitations: [],
            provider: 'deterministic_reasoner',
          },
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    ),
  )
  vi.stubGlobal('fetch', fetchMock)
  await getInvestigation('spk-1')
  const investigationCall = fetchMock.mock.calls.at(0)
  expect(investigationCall).toBeDefined()
  expect(String(investigationCall?.[0])).toContain(
    '/api/spikes/spk-1/investigation?provider=deterministic',
  )
})

test('large CSV uploads use the chunked begin/part/finish contract', async () => {
  vi.stubEnv('VITE_API_BASE_URL', 'http://api.test:9000')
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/custom/upload/begin')) {
      return Promise.resolve(
        new Response(JSON.stringify({ upload_id: 'upl-test', chunk_bytes: 8 }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }
    if (url.endsWith('/api/custom/upload/finish')) {
      return Promise.resolve(
        new Response(JSON.stringify({ session_id: 'cxs-chunked', filename: 'big.csv' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }
    return Promise.resolve(new Response(JSON.stringify({ detail: url }), { status: 404 }))
  })
  vi.stubGlobal('fetch', fetchMock)

  const parts: string[] = []
  class MockXHR {
    status = 0
    responseText = ''
    upload = { onprogress: null }
    onload: (() => void) | null = null
    onerror: (() => void) | null = null
    private headers: Record<string, string> = {}

    open() {}
    setRequestHeader(key: string, value: string) {
      this.headers[key] = value
    }
    send(body?: Blob) {
      parts.push(this.headers['X-Part-Index'] ?? '')
      void body
      this.status = 200
      this.responseText = JSON.stringify({ ok: true })
      this.onload?.()
    }
  }
  vi.stubGlobal('XMLHttpRequest', MockXHR as unknown as typeof XMLHttpRequest)

  const file = new File(['abcdefghijklmnop'], 'big.csv', { type: 'text/csv' })
  const payload = await uploadCustomCsv(file, undefined, { chunkBytes: 8 })
  expect(payload.session_id).toBe('cxs-chunked')
  expect(parts).toEqual(['0', '1'])
  expect(fetchMock.mock.calls.some((call) => String(call[0]).endsWith('/api/custom/upload/begin'))).toBe(true)
  expect(fetchMock.mock.calls.some((call) => String(call[0]).endsWith('/api/custom/upload/finish'))).toBe(true)
})
