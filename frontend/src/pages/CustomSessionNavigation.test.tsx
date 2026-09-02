import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { rememberCustomSession } from '../api/customSession'
import { ActionSessionProvider } from '../context/ActionSessionContext'
import { ApiStatusProvider } from '../context/ApiStatusContext'
import { CustomAnomalyPage } from './CustomAnomalyPage'
import { CustomUploadPage } from './CustomUploadPage'
import { installApiMock, seedEmptyCustomInvestigations } from '../test/mockApi'

afterEach(() => {
  vi.unstubAllGlobals()
})

function renderBring(path: string, seed: 'completed-a' | 'empty' = 'completed-a') {
  const fetchMock = installApiMock()
  if (seed === 'empty') seedEmptyCustomInvestigations()
  render(
    <MemoryRouter initialEntries={[path]}>
      <ApiStatusProvider>
        <ActionSessionProvider>
          <Routes>
            <Route path="/bring" element={<CustomUploadPage />} />
            <Route path="/bring/:sessionId" element={<CustomUploadPage />} />
            <Route path="/bring/:sessionId/anomalies/:anomalyId" element={<CustomAnomalyPage />} />
          </Routes>
        </ActionSessionProvider>
      </ApiStatusProvider>
    </MemoryRouter>,
  )
  return fetchMock
}

function analyzeCalls(fetchMock: ReturnType<typeof installApiMock>) {
  return fetchMock.mock.calls.filter((call) => {
    const url = String(call[0])
    const method = ((call[1] as RequestInit | undefined)?.method ?? 'GET').toUpperCase()
    return url.includes('/analyze') && method === 'POST'
  })
}

test('back to anomalies reuses the analyzed session without re-upload or re-analysis', async () => {
  const user = userEvent.setup()
  const fetchMock = renderBring('/bring/cxs-mock/anomalies/cda-a')

  expect(await screen.findByRole('heading', { name: 'Unusual transaction concentration' })).toBeInTheDocument()
  expect(screen.getAllByRole('link', { name: '← Back to anomalies' }).length).toBeGreaterThan(0)
  expect(screen.getByRole('tab', { name: 'Decision' })).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Approval' }))
  expect(screen.getByText('APPROVED')).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Simulation' }))
  expect(screen.getByText('SIMULATION COMPLETED')).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Audit history' }))
  expect(screen.getByText('Decision recorded')).toBeInTheDocument()
  expect(screen.getByText('Simulation completed')).toBeInTheDocument()

  await user.click(screen.getAllByRole('link', { name: '← Back to anomalies' })[0])
  expect(await screen.findByRole('heading', { name: 'Anomalies' })).toBeInTheDocument()
  expect(screen.getByText('Unusual transaction concentration')).toBeInTheDocument()
  expect(screen.getByText('Unusual transaction activity')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Continue with anomaly investigation' })).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Upload CSV' })).not.toBeInTheDocument()
  expect(analyzeCalls(fetchMock)).toHaveLength(0)

  await user.click(screen.getByRole('link', { name: /Unusual transaction activity/ }))
  expect(await screen.findByRole('heading', { name: 'Unusual transaction activity' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Record this decision' })).toBeInTheDocument()
  expect(screen.queryByText('Decision recorded')).not.toBeInTheDocument()

  await user.click(screen.getAllByRole('link', { name: '← Back to anomalies' })[0])
  expect(await screen.findByRole('heading', { name: 'Anomalies' })).toBeInTheDocument()
  await user.click(screen.getByRole('link', { name: /Unusual transaction concentration/ }))
  expect(await screen.findByRole('heading', { name: 'Unusual transaction concentration' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Record this decision' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Decision' }))
  expect(screen.getByText('Decision recorded')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Record this decision' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Approval' }))
  expect(screen.getByText('APPROVED')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Simulation' }))
  expect(screen.getByText('SIMULATION COMPLETED')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Run dry-run simulation' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Audit history' }))
  const panel = screen.getByRole('tabpanel')
  expect(within(panel).getByText('Decision recorded')).toBeInTheDocument()
  expect(within(panel).getByText('Approval recorded')).toBeInTheDocument()
  expect(within(panel).getByText('Simulation completed')).toBeInTheDocument()
  expect(within(panel).queryByRole('link', { name: '← Back to anomalies' })).not.toBeInTheDocument()
  expect(analyzeCalls(fetchMock)).toHaveLength(0)
})

test('completing A then reopening A restores investigation state without touching B', async () => {
  const user = userEvent.setup()
  const fetchMock = renderBring('/bring/cxs-mock/anomalies/cda-a', 'empty')

  expect(await screen.findByRole('button', { name: 'Record this decision' })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Record this decision' }))
  expect(await screen.findByRole('button', { name: 'Approve' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Record this decision' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Approve' }))
  expect(await screen.findByRole('button', { name: 'Run dry-run simulation' })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Run dry-run simulation' }))
  expect(await screen.findByText('Simulation completed')).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Approval' }))
  expect(screen.getByText('APPROVED')).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Simulation' }))
  expect(screen.getByText('SIMULATION COMPLETED')).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Audit history' }))
  const firstAudit = screen.getByRole('tabpanel')
  expect(within(firstAudit).getByText('Decision recorded')).toBeInTheDocument()
  expect(within(firstAudit).getByText('Action proposed')).toBeInTheDocument()
  expect(within(firstAudit).getByText('Approval recorded')).toBeInTheDocument()
  expect(within(firstAudit).getByText('Simulation completed')).toBeInTheDocument()
  expect(within(firstAudit).getAllByText(/Decision recorded|Action proposed|Approval recorded|Simulation completed/).length).toBe(4)

  await user.click(screen.getAllByRole('link', { name: '← Back to anomalies' })[0])
  expect(await screen.findByRole('heading', { name: 'Anomalies' })).toBeInTheDocument()
  await user.click(screen.getByRole('link', { name: /Unusual transaction concentration/ }))
  expect(await screen.findByRole('heading', { name: 'Unusual transaction concentration' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Record this decision' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Decision' }))
  expect(screen.queryByRole('button', { name: 'Record this decision' })).not.toBeInTheDocument()
  expect(screen.getByText('Decision recorded')).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Approval' }))
  expect(screen.getByText('APPROVED')).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Simulation' }))
  expect(screen.getByText('SIMULATION COMPLETED')).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Audit history' }))
  const reopened = screen.getByRole('tabpanel')
  expect(within(reopened).getByText('Decision recorded')).toBeInTheDocument()
  expect(within(reopened).getByText('Action proposed')).toBeInTheDocument()
  expect(within(reopened).getByText('Approval recorded')).toBeInTheDocument()
  expect(within(reopened).getByText('Simulation completed')).toBeInTheDocument()
  expect(within(reopened).queryByRole('link', { name: '← Back to anomalies' })).not.toBeInTheDocument()

  await user.click(screen.getAllByRole('link', { name: '← Back to anomalies' })[0])
  await user.click(await screen.findByRole('link', { name: /Unusual transaction activity/ }))
  expect(await screen.findByRole('heading', { name: 'Unusual transaction activity' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Record this decision' })).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Approval' }))
  expect(screen.getByText('PENDING')).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Simulation' }))
  expect(screen.getByText('NOT SIMULATED')).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Audit history' }))
  expect(screen.getByText('No audit events have been recorded yet.')).toBeInTheDocument()

  await user.click(screen.getAllByRole('link', { name: '← Back to anomalies' })[0])
  await user.click(await screen.findByRole('link', { name: /Unusual transaction concentration/ }))
  expect(await screen.findByRole('heading', { name: 'Unusual transaction concentration' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Record this decision' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Simulation' }))
  expect(screen.getByText('SIMULATION COMPLETED')).toBeInTheDocument()
  expect(analyzeCalls(fetchMock)).toHaveLength(0)
})

test('user-provided labels are shown as evaluation-only ground truth', async () => {
  renderBring('/bring/cxs-mock/anomalies/cda-a')
  expect(await screen.findByText('USER-PROVIDED GROUND TRUTH')).toBeInTheDocument()
  expect(screen.getByText(/Evaluation only/)).toBeInTheDocument()
  expect(screen.getByText(/Never treated as a model feature/)).toBeInTheDocument()
  expect(screen.getByText(/system's own fraud decision/)).toBeInTheDocument()
  expect(screen.getByText('Detection reasoning')).toBeInTheDocument()
  expect(screen.getByText('Classifier evidence')).toBeInTheDocument()
})

test('refreshing the session URL restores the anomaly list from the backend session', async () => {
  rememberCustomSession('cxs-mock')
  const fetchMock = renderBring('/bring/cxs-mock')
  expect(await screen.findByRole('heading', { name: 'Anomalies' })).toBeInTheDocument()
  expect(screen.getByText('Unusual transaction concentration')).toBeInTheDocument()
  expect(screen.getByText('Unusual transaction activity')).toBeInTheDocument()
  expect(analyzeCalls(fetchMock)).toHaveLength(0)
})

test('opening /bring after an active session returns to that session list', async () => {
  rememberCustomSession('cxs-mock')
  const fetchMock = renderBring('/bring')
  expect(await screen.findByRole('heading', { name: 'Anomalies' })).toBeInTheDocument()
  expect(screen.getByText('Unusual transaction concentration')).toBeInTheDocument()
  expect(analyzeCalls(fetchMock)).toHaveLength(0)
})
