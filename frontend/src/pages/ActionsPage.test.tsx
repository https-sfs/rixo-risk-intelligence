import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { HUMAN_APPROVAL_REQUIRED, SIMULATION_ONLY } from '../api/constants'
import { ActionSessionProvider } from '../context/ActionSessionContext'
import { ApiStatusProvider } from '../context/ApiStatusContext'
import { ActionsPage } from './ActionsPage'
import { actionState, approval, execution, proposal } from '../test/fixtures'
import { defaultApiResponse, installApiMock, jsonResponse } from '../test/mockApi'

afterEach(() => {
  vi.unstubAllGlobals()
})

function renderActions() {
  render(
    <MemoryRouter>
      <ApiStatusProvider>
        <ActionSessionProvider>
          <ActionsPage />
        </ActionSessionProvider>
      </ApiStatusProvider>
    </MemoryRouter>,
  )
}

test('actions page uses simulation-only wording', async () => {
  installApiMock()
  renderActions()
  expect(await screen.findByRole('heading', { name: 'Actions' })).toBeInTheDocument()
  expect(screen.getAllByText(SIMULATION_ONLY).length).toBeGreaterThan(0)
  expect(screen.getByText(new RegExp(HUMAN_APPROVAL_REQUIRED))).toBeInTheDocument()
  expect(screen.queryByText(/^Verified$/)).not.toBeInTheDocument()
  expect(screen.queryByText(/Action executed/i)).not.toBeInTheDocument()
})

test('recorded simulation is labeled simulation recorded, not verified production action', async () => {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input))
    if (url.pathname === '/api/audit') {
      return jsonResponse({
        events: [
          {
            event_id: 'aud-1',
            event_type: 'ACTION_SIMULATED',
            timestamp: '2026-01-18T03:07:00Z',
            spike_id: proposal.spike_id,
            action_id: proposal.action_id,
            actor: 'system',
            details: {},
          },
        ],
        count: 1,
      })
    }
    if (url.pathname === `/api/actions/${proposal.action_id}`) {
      return jsonResponse(
        actionState({
          approval,
          execution,
          verification: execution.verification,
          proposal: { ...proposal, status: 'simulated' },
        }),
      )
    }
    return defaultApiResponse(input, init)
  })
  vi.stubGlobal('fetch', fetchMock)

  renderActions()
  expect(await screen.findByText('Simulation recorded')).toBeInTheDocument()
  expect(screen.getByText(/Simulation executed/)).toBeInTheDocument()
  expect(screen.queryByText(/^Verified$/)).not.toBeInTheDocument()
  expect(screen.queryByText(/money saved/i)).not.toBeInTheDocument()
})

test('unapproved action shows human approval required', async () => {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input))
    if (url.pathname === '/api/audit') {
      return jsonResponse({
        events: [
          {
            event_id: 'aud-0',
            event_type: 'ACTION_PROPOSED',
            timestamp: '2026-01-18T03:05:00Z',
            spike_id: proposal.spike_id,
            action_id: proposal.action_id,
            actor: 'analyst',
            details: {},
          },
        ],
        count: 1,
      })
    }
    return defaultApiResponse(input, init)
  })
  vi.stubGlobal('fetch', fetchMock)

  renderActions()
  expect(await screen.findByText('Not simulated')).toBeInTheDocument()
  expect(screen.getByText(HUMAN_APPROVAL_REQUIRED)).toBeInTheDocument()
})
