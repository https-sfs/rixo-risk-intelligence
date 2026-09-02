import { afterEach, expect, test, vi } from 'vitest'
import { getApiBaseUrl, getInvestigation, listSpikes } from './client'

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
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
