import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { ActionSessionProvider } from '../context/ActionSessionContext'
import { ApiStatusProvider } from '../context/ApiStatusContext'
import { InvestigationDetailPage } from './InvestigationDetailPage'
import { InvestigationsPage } from './InvestigationsPage'
import { COORD_ID } from '../test/fixtures'
import { installApiMock, resetSyntheticInvestigations } from '../test/mockApi'

afterEach(() => {
  resetSyntheticInvestigations()
  vi.unstubAllGlobals()
})

function renderSynthetic(path: string, fetchMock = installApiMock()) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <ApiStatusProvider>
        <ActionSessionProvider>
          <Routes>
            <Route path="/investigations" element={<InvestigationsPage />} />
            <Route path="/investigations/:spikeId" element={<InvestigationDetailPage />} />
          </Routes>
        </ActionSessionProvider>
      </ApiStatusProvider>
    </MemoryRouter>,
  )
  return fetchMock
}

async function completeCoordinatedWorkflow(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: 'Record this decision' }))
  await user.click(await screen.findByRole('button', { name: 'Approve' }))
  await user.click(await screen.findByRole('button', { name: 'Run dry-run simulation' }))
  expect(await screen.findByText('Simulation completed')).toBeInTheDocument()
}

async function expectCompletedTabs(user: ReturnType<typeof userEvent.setup>) {
  expect(screen.queryByRole('button', { name: 'Record this decision' })).not.toBeInTheDocument()
  expect(screen.queryByText(/Approved by/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/SIMULATION RECORDED/)).not.toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Decision' }))
  expect(screen.getByText('Decision recorded')).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Approval' }))
  expect(screen.getByText('APPROVED')).toBeInTheDocument()
  expect(screen.getByText('Approval recorded')).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Simulation' }))
  expect(screen.getByText('SIMULATION COMPLETED')).toBeInTheDocument()
  expect(screen.getByText('Simulation impact')).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Audit history' }))
  const panel = screen.getByRole('tabpanel')
  expect(within(panel).getByText('Decision recorded')).toBeInTheDocument()
  expect(within(panel).getByText('Action proposed')).toBeInTheDocument()
  expect(within(panel).getByText('Approval recorded')).toBeInTheDocument()
  expect(within(panel).getByText('Simulation completed')).toBeInTheDocument()
  expect(within(panel).getByText('Simulation verified')).toBeInTheDocument()
}

function proposeCalls(fetchMock: ReturnType<typeof vi.fn>) {
  return fetchMock.mock.calls.filter(
    (call) =>
      String(call[0]).includes('/api/actions/propose') &&
      ((call[1] as RequestInit | undefined)?.method ?? 'GET').toUpperCase() === 'POST',
  )
}

test('synthetic anomaly with no investigation state starts at the initial decision', async () => {
  renderSynthetic(`/investigations/${COORD_ID}`)
  expect(await screen.findByRole('heading', { name: 'Investigation workflow' })).toBeInTheDocument()
  expect(screen.getByText('1. Decision → 2. Approval → 3. Simulation → 4. Audit')).toBeInTheDocument()
  expect(await screen.findByRole('button', { name: 'Record this decision' })).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: 'Decision' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.queryByText(/Approved by/i)).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Run dry-run simulation' })).not.toBeInTheDocument()
  expect(screen.queryByText('Action proposed')).not.toBeInTheDocument()
})

test('completed synthetic anomaly restores decision, approval, simulation, and audit on reopen', async () => {
  const user = userEvent.setup()
  const fetchMock = renderSynthetic(`/investigations/${COORD_ID}`)
  await completeCoordinatedWorkflow(user)
  const auditPanel = screen.getByRole('tabpanel')
  expect(within(auditPanel).getByText('Decision recorded')).toBeInTheDocument()
  expect(within(auditPanel).getByText('Action proposed')).toBeInTheDocument()
  expect(within(auditPanel).getByText('Approval recorded')).toBeInTheDocument()
  expect(within(auditPanel).getByText('Simulation completed')).toBeInTheDocument()
  expect(within(auditPanel).getByText('Simulation verified')).toBeInTheDocument()

  await user.click(screen.getAllByRole('link', { name: '← Investigations' })[0])
  expect(await screen.findByRole('heading', { name: 'Investigations' })).toBeInTheDocument()
  await user.click(screen.getByRole('link', { name: /Case #2/ }))

  expect(await screen.findByRole('heading', { name: 'Case #2' })).toBeInTheDocument()
  await expectCompletedTabs(user)
  expect(proposeCalls(fetchMock)).toHaveLength(1)
})

test('synthetic anomaly B stays empty after A is completed', async () => {
  const user = userEvent.setup()
  renderSynthetic(`/investigations/${COORD_ID}`)
  await completeCoordinatedWorkflow(user)

  await user.click(screen.getByRole('link', { name: 'Festive demo' }))
  expect(await screen.findByRole('heading', { name: 'Case #18' })).toBeInTheDocument()
  expect(await screen.findByRole('button', { name: 'Record this decision' })).toBeInTheDocument()
  expect(screen.queryByText(/Approved by/i)).not.toBeInTheDocument()
  expect(screen.queryByText('Action proposed')).not.toBeInTheDocument()
  expect(screen.queryByText(/SIMULATION RECORDED/)).not.toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Audit history' }))
  expect(screen.getByText('No audit events have been recorded yet.')).toBeInTheDocument()
})

test('refreshing the synthetic anomaly URL restores the same persisted state', async () => {
  const user = userEvent.setup()
  const fetchMock = installApiMock()
  const { unmount } = render(
    <MemoryRouter initialEntries={[`/investigations/${COORD_ID}`]}>
      <ApiStatusProvider>
        <ActionSessionProvider>
          <Routes>
            <Route path="/investigations/:spikeId" element={<InvestigationDetailPage />} />
          </Routes>
        </ActionSessionProvider>
      </ApiStatusProvider>
    </MemoryRouter>,
  )
  await completeCoordinatedWorkflow(user)
  expect(proposeCalls(fetchMock)).toHaveLength(1)
  unmount()

  render(
    <MemoryRouter initialEntries={[`/investigations/${COORD_ID}`]}>
      <ApiStatusProvider>
        <ActionSessionProvider>
          <Routes>
            <Route path="/investigations/:spikeId" element={<InvestigationDetailPage />} />
          </Routes>
        </ActionSessionProvider>
      </ApiStatusProvider>
    </MemoryRouter>,
  )
  expect(await screen.findByRole('heading', { name: 'Case #2' })).toBeInTheDocument()
  await expectCompletedTabs(user)
  expect(proposeCalls(fetchMock)).toHaveLength(1)
})
