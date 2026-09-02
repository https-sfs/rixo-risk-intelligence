import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { ActionSessionProvider } from '../context/ActionSessionContext'
import { ApiStatusProvider } from '../context/ApiStatusContext'
import { InvestigationDetailPage } from './InvestigationDetailPage'
import { SIMULATION_ONLY, SYNTHETIC_SCENARIO } from '../api/constants'
import {
  actionState,
  approval,
  COORD_ID,
  execution,
  FEST_ID,
  proposal,
} from '../test/fixtures'
import { defaultApiResponse, installApiMock, jsonResponse, resetSyntheticInvestigations } from '../test/mockApi'

afterEach(() => {
  resetSyntheticInvestigations()
  vi.unstubAllGlobals()
})

function renderDetail(spikeId: string, fetchMock = installApiMock()) {
  render(
    <MemoryRouter initialEntries={[`/investigations/${spikeId}`]}>
      <ApiStatusProvider>
        <ActionSessionProvider>
          <Routes>
            <Route path="/investigations/:spikeId" element={<InvestigationDetailPage />} />
          </Routes>
        </ActionSessionProvider>
      </ApiStatusProvider>
    </MemoryRouter>,
  )
  return fetchMock
}

function workflowMock() {
  resetSyntheticInvestigations()
  let approved = false
  let executed = false
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input))
    if (url.pathname.endsWith('/approve')) {
      approved = true
      return jsonResponse(approval)
    }
    if (url.pathname.endsWith('/execute')) {
      executed = true
      return jsonResponse(execution)
    }
    if (url.pathname === `/api/actions/${proposal.action_id}`) {
      return jsonResponse(
        actionState({
          approval: approved ? approval : null,
          execution: executed ? execution : null,
          verification: executed ? execution.verification : null,
          proposal: {
            ...proposal,
            status: executed ? 'simulated' : approved ? 'approved' : 'proposed',
          },
        }),
      )
    }
    return defaultApiResponse(input, init)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

test('investigation detail loads spike metadata and the 4-stage workflow', async () => {
  renderDetail(COORD_ID)
  expect(await screen.findByRole('heading', { name: 'Case #2' })).toBeInTheDocument()
  expect(screen.getByText(/Fraud spike investigation/i)).toBeInTheDocument()
  expect(screen.getByText(new RegExp(SYNTHETIC_SCENARIO))).toBeInTheDocument()
  expect(screen.getByText(/SEED 42/)).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Investigation workflow' })).toBeInTheDocument()
  expect(screen.getByText('1. Decision → 2. Approval → 3. Simulation → 4. Audit')).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: 'Decision' })).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: 'Approval' })).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: 'Simulation' })).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: 'Audit history' })).toBeInTheDocument()
  expect(screen.queryByText('1. DETECTED')).not.toBeInTheDocument()
  expect(screen.queryByText('2. EVIDENCE')).not.toBeInTheDocument()
  expect(screen.queryByText('3. INVESTIGATE')).not.toBeInTheDocument()
  expect(screen.queryByText('4. DECIDE')).not.toBeInTheDocument()
  expect(screen.queryByText('5. HUMAN APPROVAL')).not.toBeInTheDocument()
  expect(screen.queryByText('6. SIMULATE')).not.toBeInTheDocument()
  expect(screen.queryByText('7. VERIFY')).not.toBeInTheDocument()
  expect(screen.getByText(/Human approval is required/)).toBeInTheDocument()
  expect(screen.getByText(new RegExp(SIMULATION_ONLY))).toBeInTheDocument()
  expect(screen.getAllByText('coordinated abuse').length).toBeGreaterThan(0)
  expect(screen.getAllByText('88%').length).toBeGreaterThan(0)
  expect(screen.queryByText(/fraud prevented/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/money protected/i)).not.toBeInTheDocument()
  expect(screen.getByText('Investigator summary')).toBeInTheDocument()
  expect(screen.getByTestId('investigation-agent')).toBeInTheDocument()
  expect(screen.getByText('Investigation agent')).toBeInTheDocument()
  expect(screen.getByText(/Bounded read-only investigation using available case evidence/)).toBeInTheDocument()
  expect(screen.getByText(/inspect case metrics · completed/)).toBeInTheDocument()
  const agent = screen.getByTestId('investigation-agent')
  expect(within(agent).queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
  expect(within(agent).queryByRole('button', { name: 'Run dry-run simulation' })).not.toBeInTheDocument()
  expect(within(agent).queryByRole('textbox')).not.toBeInTheDocument()
  expect(within(agent).queryByText(/confirmed fraud/i)).not.toBeInTheDocument()
  expect(screen.getByText('Why this case was flagged')).toBeInTheDocument()
  expect(screen.getByText('Potential false-positive impact')).toBeInTheDocument()
  expect(screen.getByText('Classifier evidence')).toBeInTheDocument()
  expect(screen.getByText('Detection reasoning')).toBeInTheDocument()
  expect(screen.getByText('High risk')).toBeInTheDocument()
  expect(
    screen.getByText(/Classifier scores are reported separately and did not produce this verdict/),
  ).toBeInTheDocument()
  expect(screen.getByText('Concentrated entities and failed payments indicate coordination.')).toBeInTheDocument()
  expect(
    screen.queryByText(/Classifier output is available as supporting evidence/),
  ).not.toBeInTheDocument()
})

test('supporting and contradicting evidence render', async () => {
  renderDetail(COORD_ID)
  expect(
    await screen.findByText('94.67% of transactions share subnet 45.33.32.0/24'),
  ).toBeInTheDocument()
  expect(screen.getByText(/concentration.subnets.top_share/)).toBeInTheDocument()
  expect(screen.getByText('A minority of accounts look ordinary shoppers.')).toBeInTheDocument()
  expect(screen.getByText('What could explain this?')).toBeInTheDocument()
})

test('Decision tab starts ready to record and is not pre-approved', async () => {
  renderDetail(COORD_ID)
  expect(await screen.findByText('Tighten rule')).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: 'Decision' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByRole('button', { name: 'Record this decision' })).toBeInTheDocument()
  expect(screen.queryByText(/Approved by/i)).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Run dry-run simulation' })).not.toBeInTheDocument()
})

test('Approval tab stays gated until a decision is recorded', async () => {
  const user = userEvent.setup()
  renderDetail(COORD_ID)
  await screen.findByRole('button', { name: 'Record this decision' })
  await user.click(screen.getByRole('tab', { name: 'Approval' }))
  const panel = screen.getByRole('tabpanel')
  expect(within(panel).getByText('Approval required')).toBeInTheDocument()
  expect(within(panel).getByText('PENDING')).toBeInTheDocument()
  expect(within(panel).getByText('A decision must be recorded before approval can be granted.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
})

test('Simulation tab stays gated until approval', async () => {
  const user = userEvent.setup()
  renderDetail(COORD_ID)
  await screen.findByRole('button', { name: 'Record this decision' })
  await user.click(screen.getByRole('tab', { name: 'Simulation' }))
  const panel = screen.getByRole('tabpanel')
  expect(within(panel).getByText('NOT SIMULATED')).toBeInTheDocument()
  expect(
    within(panel).getByText('Human approval is required before this dry-run can be recorded.'),
  ).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Run dry-run simulation' })).not.toBeInTheDocument()
})

test('Audit history tab is empty before any action is recorded', async () => {
  const user = userEvent.setup()
  renderDetail(COORD_ID)
  await screen.findByRole('button', { name: 'Record this decision' })
  await user.click(screen.getByRole('tab', { name: 'Audit history' }))
  const panel = screen.getByRole('tabpanel')
  expect(within(panel).getByText('Audit history')).toBeInTheDocument()
  expect(within(panel).getByText('No audit events have been recorded yet.')).toBeInTheDocument()
})

test('approval calls the approve endpoint and simulation stays hidden until then', async () => {
  const fetchMock = workflowMock()
  renderDetail(COORD_ID, fetchMock)
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Record this decision' }))
  expect(await screen.findByRole('button', { name: 'Approve' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Run dry-run simulation' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Approve' }))
  await waitFor(() => {
    expect(
      fetchMock.mock.calls.some(
        (call) =>
          String(call[0]).includes(`/api/actions/${proposal.action_id}/approve`) &&
          ((call[1] as RequestInit | undefined)?.method ?? 'GET').toUpperCase() === 'POST',
      ),
    ).toBe(true)
  })
  expect(screen.queryByText(/Approved by/i)).not.toBeInTheDocument()
  expect(await screen.findByRole('button', { name: 'Run dry-run simulation' })).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Approval' }))
  expect(screen.getByText('Approval recorded')).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Simulation' }))
  expect(screen.getByText('Simulation impact')).toBeInTheDocument()
  expect(
    screen.getByText(
      /demonstrates the action that would be taken in a production fraud-response environment/,
    ),
  ).toBeInTheDocument()
  expect(screen.getByText('Payment: Would block the flagged payment in a live deployment.')).toBeInTheDocument()
  expect(
    screen.getByText('Execution: Simulated only — no live payment is executed.'),
  ).toBeInTheDocument()
  expect(screen.queryByText(/Payment executed/i)).not.toBeInTheDocument()
})

test('simulation success renders only after the execute API succeeds', async () => {
  const fetchMock = workflowMock()
  renderDetail(COORD_ID, fetchMock)
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Record this decision' }))
  await user.click(await screen.findByRole('button', { name: 'Approve' }))
  expect(screen.queryByText('SIMULATION COMPLETED')).not.toBeInTheDocument()
  await user.click(await screen.findByRole('button', { name: 'Run dry-run simulation' }))
  expect(screen.queryByText(/SIMULATION RECORDED/)).not.toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Simulation' }))
  expect(await screen.findByText('SIMULATION COMPLETED')).toBeInTheDocument()
  expect(screen.getAllByText(/TEST MODE ONLY/).length).toBeGreaterThan(0)
  expect(screen.getByText('Simulation impact')).toBeInTheDocument()
  expect(
    screen.getByText('Merchant account: Would apply the approved merchant-account action in a live deployment.'),
  ).toBeInTheDocument()
  expect(
    screen.getByText('Money movement: Simulated only — no real money is moved.'),
  ).toBeInTheDocument()
  expect(screen.getByText('Razorpay TEST simulation')).toBeInTheDocument()
  expect(
    screen.getByText(
      'Demonstrates the corresponding payment-system operation using Razorpay Test Mode. No real payment or money movement occurs.',
    ),
  ).toBeInTheDocument()
  expect(screen.getAllByText(/configuration missing/).length).toBeGreaterThan(0)
  expect(screen.queryByText(/fraud prevented/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/intervention successful/i)).not.toBeInTheDocument()
  expect(
    fetchMock.mock.calls.some(
      (call) =>
        String(call[0]).includes(`/api/actions/${proposal.action_id}/execute`) &&
        ((call[1] as RequestInit | undefined)?.method ?? 'GET').toUpperCase() === 'POST',
    ),
  ).toBe(true)
})

test('API errors are shown without fabricating success', async () => {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = new URL(String(input))
    if (url.pathname === '/api/health') {
      return jsonResponse({ status: 'ok', service: 's', component: 'c' })
    }
    return jsonResponse({ detail: 'unknown spike' }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  renderDetail('spk-missing', fetchMock)
  expect(await screen.findByText('Investigation unavailable')).toBeInTheDocument()
  expect(screen.getByText('unknown spike')).toBeInTheDocument()
  expect(screen.queryByText(/Simulation verified/i)).not.toBeInTheDocument()
})

test('festive investigation does not show tighten_rule when monitor is recommended', async () => {
  renderDetail(FEST_ID)
  expect((await screen.findAllByText('likely festive')).length).toBeGreaterThan(0)
  expect(screen.getByText('Monitor')).toBeInTheDocument()
  expect(screen.getByText(/NO TIGHTEN_RULE/)).toBeInTheDocument()
  expect(screen.queryByText(/^tighten rule$/i)).not.toBeInTheDocument()
  expect(screen.getByText(/No tightening action recommended/i)).toBeInTheDocument()
})
