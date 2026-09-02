import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { ActionSessionProvider } from '../context/ActionSessionContext'
import { ApiStatusProvider } from '../context/ApiStatusContext'
import { RecentAnomalyPage } from './RecentAnomalyPage'
import { RecentOverviewPage } from './RecentOverviewPage'
import { installApiMock } from '../test/mockApi'

afterEach(() => {
  vi.unstubAllGlobals()
})

function renderRecent(path: string) {
  const fetchMock = installApiMock()
  render(
    <MemoryRouter initialEntries={[path]}>
      <ApiStatusProvider>
        <ActionSessionProvider>
          <Routes>
            <Route path="/recent" element={<RecentOverviewPage />} />
            <Route path="/recent/anomalies/:anomalyId" element={<RecentAnomalyPage />} />
          </Routes>
        </ActionSessionProvider>
      </ApiStatusProvider>
    </MemoryRouter>,
  )
  return fetchMock
}

test('January 2026 anomaly #20 keeps completed investigation after back and reopen', async () => {
  const user = userEvent.setup()
  renderRecent('/recent/anomalies/rct-20260104-20')

  expect(await screen.findByRole('button', { name: 'Record this decision' })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Record this decision' }))
  expect(await screen.findByRole('button', { name: 'Approve' })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Approve' }))
  expect(await screen.findByRole('button', { name: 'Run dry-run simulation' })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Run dry-run simulation' }))
  expect(await screen.findByText('Simulation completed')).toBeInTheDocument()

  await user.click(screen.getAllByRole('link', { name: '← Back to anomalies' })[0])
  expect(await screen.findByText('Anomaly #20')).toBeInTheDocument()
  await user.click(screen.getByRole('link', { name: 'Amount concentration' }))

  expect(await screen.findByRole('heading', { name: '2026 ONLINE BANKING FRAUD DATA' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Record this decision' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Decision' }))
  expect(screen.getByText('Decision recorded')).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Approval' }))
  expect(screen.getByText('APPROVED')).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Simulation' }))
  expect(screen.getByText('SIMULATION COMPLETED')).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Audit history' }))
  const panel = screen.getByRole('tabpanel')
  expect(within(panel).getByText('Decision recorded')).toBeInTheDocument()
  expect(within(panel).getByText('Action proposed')).toBeInTheDocument()
  expect(within(panel).getByText('Approval recorded')).toBeInTheDocument()
  expect(within(panel).getByText('Simulation completed')).toBeInTheDocument()

  await user.click(screen.getAllByRole('link', { name: '← Back to anomalies' })[0])
  await user.click(await screen.findByRole('link', { name: 'Temporal anomaly' }))
  expect(await screen.findByRole('button', { name: 'Record this decision' })).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Audit history' }))
  expect(screen.getByText('No audit events have been recorded yet.')).toBeInTheDocument()

  await user.click(screen.getAllByRole('link', { name: '← Back to anomalies' })[0])
  await user.click(await screen.findByRole('link', { name: 'Amount concentration' }))
  expect(await screen.findByRole('heading', { name: '2026 ONLINE BANKING FRAUD DATA' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Record this decision' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Simulation' }))
  expect(screen.getByText('SIMULATION COMPLETED')).toBeInTheDocument()
})
