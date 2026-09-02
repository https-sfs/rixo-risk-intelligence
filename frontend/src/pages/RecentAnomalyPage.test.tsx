import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { ActionSessionProvider } from '../context/ActionSessionContext'
import { ApiStatusProvider } from '../context/ApiStatusContext'
import { RecentAnomalyPage } from './RecentAnomalyPage'
import { defaultApiResponse, installApiMock, jsonResponse } from '../test/mockApi'

afterEach(() => {
  vi.unstubAllGlobals()
})

test('recent investigation uses delayed ground truth and excludes source-model AI claims', async () => {
  installApiMock()
  render(
    <MemoryRouter initialEntries={['/recent/anomalies/rct-20260115-14']}>
      <ApiStatusProvider>
        <ActionSessionProvider>
          <Routes>
            <Route path="/recent/anomalies/:anomalyId" element={<RecentAnomalyPage />} />
          </Routes>
        </ActionSessionProvider>
      </ApiStatusProvider>
    </MemoryRouter>,
  )
  expect(await screen.findByText(/Anomaly: Unusual transaction activity/)).toBeInTheDocument()
  expect(screen.getByText('2026 ONLINE BANKING FRAUD DATA')).toBeInTheDocument()
  expect(screen.getByText('Investigator summary')).toBeInTheDocument()
  expect(screen.getByText('MODEL EVIDENCE: LIMITED')).toBeInTheDocument()
  expect(screen.getByText('Investigation agent')).toBeInTheDocument()
  expect(screen.getByText(/Unavailable identifiers: account, device, merchant, SKU/)).toBeInTheDocument()
  expect(screen.getByText('Investigation evidence')).toBeInTheDocument()
  expect(screen.getAllByText('Derived').length).toBeGreaterThan(0)
  expect(screen.getByText('Evidence coverage')).toBeInTheDocument()
  expect(screen.getByText(/Source dataset model outputs were not used/)).toBeInTheDocument()
  expect(screen.getByText('Detection reasoning')).toBeInTheDocument()
  expect(screen.getByText('Investigation workflow')).toBeInTheDocument()
  expect(screen.getByText('Record this decision')).toBeInTheDocument()
  expect(screen.getByText('Dataset methodology & limitations')).toBeInTheDocument()
  expect(
    screen.getByText(
      /This public dataset is used for historical evaluation and validation of the investigation pipeline/,
    ),
  ).toBeInTheDocument()
  expect(
    screen.getByText(/Labelled fraud value is historical ground truth, not money saved\/prevented/),
  ).toBeInTheDocument()
  expect(
    screen.getByText(/Source-model outputs are external evidence from the source dataset/),
  ).toBeInTheDocument()
  expect(screen.queryByText(/our model detected/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/AI prediction/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/^Money saved$/i)).not.toBeInTheDocument()
  expect(screen.getByText('Classifier evidence')).toBeInTheDocument()
  expect(screen.getByText('Low risk')).toBeInTheDocument()
  expect(screen.queryByText(/The IEEE-CIS classifier was not applied/)).not.toBeInTheDocument()
  expect(screen.queryByText(/classifier was not applied/i)).not.toBeInTheDocument()
})

test('january reasoning cannot claim classifier was not applied when classifier output exists', async () => {
  installApiMock()
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/api/recent/anomalies/') && url.includes('/investigation')) {
        return jsonResponse({
          provider: 'deterministic',
          provider_label: 'DETERMINISTIC',
          headline: 'Temporal anomaly',
          summary:
            'January 2026 window. The IEEE-CIS classifier was not applied. Detection used hour-level volume and amount only.',
          signals: ['elevated transaction amount'],
          limitations: [],
          llm_used: false,
        })
      }
      return defaultApiResponse(input, init)
    }),
  )
  render(
    <MemoryRouter initialEntries={['/recent/anomalies/rct-20260108-03']}>
      <ApiStatusProvider>
        <ActionSessionProvider>
          <Routes>
            <Route path="/recent/anomalies/:anomalyId" element={<RecentAnomalyPage />} />
          </Routes>
        </ActionSessionProvider>
      </ApiStatusProvider>
    </MemoryRouter>,
  )
  expect(await screen.findByText('Classifier evidence')).toBeInTheDocument()
  expect(screen.getByText('Low risk')).toBeInTheDocument()
  expect(screen.getByText(/Supporting evidence from the shared classifier/)).toBeInTheDocument()
  expect(screen.queryByText(/The IEEE-CIS classifier was not applied/)).not.toBeInTheDocument()
  expect(screen.queryByText(/classifier was not applied/i)).not.toBeInTheDocument()
})
