import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { ActionSessionProvider } from '../context/ActionSessionContext'
import { ApiStatusProvider } from '../context/ApiStatusContext'
import { RecentOverviewPage } from './RecentOverviewPage'
import { installApiMock } from '../test/mockApi'

afterEach(() => {
  vi.unstubAllGlobals()
})

test('recent overview is a third data world with January 2026 wording', async () => {
  installApiMock()
  render(
    <MemoryRouter>
      <ApiStatusProvider>
        <ActionSessionProvider>
          <RecentOverviewPage />
        </ActionSessionProvider>
      </ApiStatusProvider>
    </MemoryRouter>,
  )
  expect(await screen.findByText('2026 ONLINE BANKING FRAUD DATA')).toBeInTheDocument()
  expect(screen.getByText(/RECENT PUBLIC DATA/)).toBeInTheDocument()
  expect(
    screen.getAllByText(/Recent public online-banking transaction data collected in January 2026/)
      .length,
  ).toBeGreaterThan(0)
  expect(screen.getByText('Observed transactions')).toBeInTheDocument()
  expect(screen.getByText('Confirmed fraud')).toBeInTheDocument()
  expect(screen.getByText('Independent fraud signals')).toBeInTheDocument()
  expect(screen.getByText('Classifier evaluation status')).toBeInTheDocument()
  expect(
    screen.getByText(/Classifier precision, recall, F1, and PR-AUC are not calculated for January 2026/),
  ).toBeInTheDocument()
  expect(screen.getByText('Recent-data anomalies')).toBeInTheDocument()
  expect(screen.getByText('Investigation evidence')).toBeInTheDocument()
  expect(screen.getByText('Evidence coverage')).toBeInTheDocument()
  expect(screen.getByText('Dataset methodology & limitations')).toBeInTheDocument()
  expect(screen.getByText('Anomaly #14')).toBeInTheDocument()
  expect(screen.queryByText('rct-20260115-14')).not.toBeInTheDocument()
  expect(screen.getAllByText(/Temporal anomaly/).length).toBeGreaterThan(0)
  expect(screen.getAllByRole('link', { name: /Zenodo record 20359708/ }).length).toBeGreaterThan(0)
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
  expect(screen.queryByText(/live fraud detection/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/our model detected/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/^Money saved$/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/AI prediction/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/IEEE-CIS Fraud Detection/)).not.toBeInTheDocument()
  expect(screen.queryByText(/SYNTHETIC SCENARIO/)).not.toBeInTheDocument()
  expect(screen.queryByText(/₹/)).not.toBeInTheDocument()
})
