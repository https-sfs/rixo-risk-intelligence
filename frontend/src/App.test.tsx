import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import App from './App'
import { installApiMock } from './test/mockApi'

afterEach(() => {
  vi.unstubAllGlobals()
})

test('app renders the operator shell', async () => {
  installApiMock()
  render(<App />)
  expect(screen.getByText('RIXO')).toBeInTheDocument()
  expect(screen.getByText(/Risk Intelligence & eXecution Operations/)).toBeInTheDocument()
  expect(screen.queryByText('Fraud-Spike Investigator')).not.toBeInTheDocument()
  expect(
    screen.queryByText(/Investigate sudden fraud spikes before they become payment risk/),
  ).not.toBeInTheDocument()
  expect(await screen.findByRole('heading', { name: 'Overview' })).toBeInTheDocument()
  expect(screen.getByText(/Demo \/ simulation environment/i)).toBeInTheDocument()
  expect(screen.getByText(/DETECT → INVESTIGATE → DECIDE → ACT → VERIFY/)).toBeInTheDocument()
  expect(screen.getAllByText(/HUMAN APPROVAL REQUIRED/).length).toBeGreaterThan(0)
  expect(screen.getAllByText(/SIMULATION ONLY/).length).toBeGreaterThan(0)
  expect(screen.queryByText(/AI Risk Operations/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/money saved/i)).not.toBeInTheDocument()
})

test('navigation opens investigations, actions, and audit', async () => {
  installApiMock()
  const user = userEvent.setup()
  render(<App />)
  await screen.findByRole('heading', { name: 'Overview' })
  await user.click(screen.getByRole('link', { name: 'Investigations' }))
  expect(await screen.findByRole('heading', { name: 'Investigations' })).toBeInTheDocument()
  expect(screen.getByText(/Synthetic investigation queue/i)).toBeInTheDocument()
  await user.click(screen.getByRole('link', { name: 'Actions' }))
  expect(await screen.findByRole('heading', { name: 'Actions' })).toBeInTheDocument()
  expect(screen.getAllByText(/SIMULATION ONLY/).length).toBeGreaterThan(0)
  await user.click(screen.getByRole('link', { name: 'Audit' }))
  expect(await screen.findByRole('heading', { name: 'Audit' })).toBeInTheDocument()
  expect(screen.getByText(/SIMULATION AUDIT TRAIL/)).toBeInTheDocument()
  await user.click(screen.getByRole('link', { name: 'IEEE-CIS' }))
  expect(await screen.findByText('IEEE-CIS Fraud Detection')).toBeInTheDocument()
  expect(screen.getByText(/REAL PUBLIC DATA — IEEE-CIS/)).toBeInTheDocument()
  expect(screen.queryByText(/SYNTHETIC SCENARIO/)).not.toBeInTheDocument()
  await user.click(screen.getByRole('link', { name: 'Jan 2026' }))
  expect(await screen.findByText('2026 ONLINE BANKING FRAUD DATA')).toBeInTheDocument()
  expect(screen.getByText(/RECENT PUBLIC DATA — January 2026/)).toBeInTheDocument()
  expect(screen.queryByText(/IEEE-CIS — no production/)).not.toBeInTheDocument()
  expect(screen.queryByText(/SYNTHETIC SCENARIO/)).not.toBeInTheDocument()
  await user.click(screen.getByRole('link', { name: 'Bring Your Data' }))
  expect(await screen.findByText('Your transactions. Our investigation engine.')).toBeInTheDocument()
  expect(screen.getByText(/BRING YOUR DATA — user-provided CSV/)).toBeInTheDocument()
  expect(screen.queryByText(/SYNTHETIC SCENARIO/)).not.toBeInTheDocument()
})
