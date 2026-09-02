import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { ActionSessionProvider } from '../context/ActionSessionContext'
import { ApiStatusProvider } from '../context/ApiStatusContext'
import { RealAnomalyPage } from './RealAnomalyPage'
import { installApiMock } from '../test/mockApi'

afterEach(() => {
  vi.unstubAllGlobals()
})

test('real investigation leads with temporal analysis, not missing-field warnings', async () => {
  installApiMock()
  render(
    <MemoryRouter initialEntries={['/real/anomalies/rda-24']}>
      <ApiStatusProvider>
        <ActionSessionProvider>
          <Routes>
            <Route path="/real/anomalies/:anomalyId" element={<RealAnomalyPage />} />
          </Routes>
        </ActionSessionProvider>
      </ApiStatusProvider>
    </MemoryRouter>,
  )
  expect(await screen.findByText(/Anomaly: Unusual transaction activity/)).toBeInTheDocument()
  expect(screen.getByText(/Period: Relative hour 24/)).toBeInTheDocument()
  expect(screen.getAllByText(/3 transactions/).length).toBeGreaterThan(0)
  expect(
    screen.getAllByText(/IEEE-CIS provides elapsed transaction time rather than calendar timestamps/)
      .length,
  ).toBeGreaterThan(0)
  expect(screen.getByText('Investigator summary')).toBeInTheDocument()
  expect(screen.getByText('MODEL EVIDENCE: CONTEXTUAL')).toBeInTheDocument()
  expect(screen.getByText('Investigation agent')).toBeInTheDocument()
  expect(screen.getByText('Detection reasoning')).toBeInTheDocument()
  expect(screen.getByText(/is a REAL DATA ANOMALY/)).toBeInTheDocument()
  expect(screen.getByText('Investigation evidence')).toBeInTheDocument()
  expect(screen.getByText('Supervised fraud-risk overlay')).toBeInTheDocument()
  expect(screen.getAllByText(/MODEL PREDICTION/).length).toBeGreaterThan(0)
  expect(screen.getAllByText(/IN_SAMPLE_MODEL_OVERLAY/).length).toBeGreaterThan(0)
  expect(
    screen.getAllByText(/not held-out test performance, not model accuracy, and not production performance/)
      .length,
  ).toBeGreaterThan(0)
  expect(screen.getAllByText('Derived').length).toBeGreaterThan(0)
  expect(
    screen.queryByText(/investigation display, not a test metric/),
  ).not.toBeInTheDocument()
  expect(screen.getByText(/Transaction 24 · score/)).toBeInTheDocument()
  expect(screen.getByText('Investigation workflow')).toBeInTheDocument()
  expect(screen.getByText(/SIMULATION ONLY/)).toBeInTheDocument()
  expect(screen.getByText('Evidence coverage')).toBeInTheDocument()
  expect(screen.getByText('ProductCD concentration')).toBeInTheDocument()
  expect(screen.queryByText(/PROXY SIGNAL/)).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: /Signal limitations/i })).not.toBeInTheDocument()
  expect(screen.getAllByText('Proxy').length).toBeGreaterThan(0)
  expect(screen.getByText('Dataset limitations & methodology')).toBeInTheDocument()
})
