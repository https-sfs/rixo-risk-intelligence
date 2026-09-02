import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { ActionSessionProvider } from '../context/ActionSessionContext'
import { ApiStatusProvider } from '../context/ApiStatusContext'
import { RealOverviewPage } from './RealOverviewPage'
import { installApiMock } from '../test/mockApi'

afterEach(() => {
  vi.unstubAllGlobals()
})

test('real overview uses IEEE-CIS wording and USD, not synthetic demo language', async () => {
  installApiMock()
  render(
    <MemoryRouter>
      <ApiStatusProvider>
        <ActionSessionProvider>
          <RealOverviewPage />
        </ActionSessionProvider>
      </ApiStatusProvider>
    </MemoryRouter>,
  )
  expect(await screen.findByText('IEEE-CIS Fraud Detection')).toBeInTheDocument()
  expect(screen.getByText(/REAL PUBLIC DATA/)).toBeInTheDocument()
  expect(screen.getByText(/Historical e-commerce fraud analysis/)).toBeInTheDocument()
  expect(screen.getByText('Anomaly #24')).toBeInTheDocument()
  expect(screen.queryByText('rda-24')).not.toBeInTheDocument()
  expect(screen.getByText('Observed transactions')).toBeInTheDocument()
  expect(screen.getByText('Evidence coverage')).toBeInTheDocument()
  expect(screen.getByText('Supervised fraud-risk layer')).toBeInTheDocument()
  expect(screen.getByText(/MODEL PREDICTION/)).toBeInTheDocument()
  expect(screen.getByText('Test PR-AUC')).toBeInTheDocument()
  expect(screen.getByText('Test precision')).toBeInTheDocument()
  expect(screen.getByText('Hour-detector holdout')).toBeInTheDocument()
  expect(screen.getByText(/not classifier test/)).toBeInTheDocument()
  expect(screen.getByText('Dataset limitations & methodology')).toBeInTheDocument()
  expect(screen.getByText(/Temporal anomaly/)).toBeInTheDocument()
  expect(
    screen.getAllByText(/elapsed transaction time rather than calendar timestamps/).length,
  ).toBeGreaterThan(0)
  expect(screen.queryByRole('heading', { name: /Signal limitations/i })).not.toBeInTheDocument()
  expect(screen.queryByText(/IP address\s+UNAVAILABLE/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/likely festive/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/simulation verified/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/₹/)).not.toBeInTheDocument()
})
