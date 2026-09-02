import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { ActionSessionProvider } from '../context/ActionSessionContext'
import { ApiStatusProvider } from '../context/ApiStatusContext'
import { OverviewPage } from './OverviewPage'
import {
  HUMAN_APPROVAL_REQUIRED,
  SIMULATION_ONLY,
  SYNTHETIC_SCENARIO,
} from '../api/constants'
import { COORD_ID, FEST_ID } from '../test/fixtures'
import { installApiMock } from '../test/mockApi'

afterEach(() => {
  vi.unstubAllGlobals()
})

test('overview renders spike aggregates from the API', async () => {
  installApiMock()
  render(
    <MemoryRouter>
      <ApiStatusProvider>
        <ActionSessionProvider>
          <OverviewPage />
        </ActionSessionProvider>
      </ApiStatusProvider>
    </MemoryRouter>,
  )
  expect((await screen.findAllByText('Case #2')).length).toBeGreaterThan(0)
  expect(screen.queryByText(COORD_ID)).not.toBeInTheDocument()
  expect(screen.getByText('Detected spikes')).toBeInTheDocument()
  expect(screen.getByText('Held-out detection metrics')).toBeInTheDocument()
  expect(screen.getByText(/not a production accuracy claim/)).toBeInTheDocument()
  expect(screen.getAllByText('2').length).toBeGreaterThan(0)
  expect(screen.getByText('High severity')).toBeInTheDocument()
  expect(screen.getByText(SYNTHETIC_SCENARIO)).toBeInTheDocument()
  expect(screen.getByText('Seed 42')).toBeInTheDocument()
  expect(
    screen.getByText(/Controlled synthetic payment world used for the reproducible demo/),
  ).toBeInTheDocument()
  expect(screen.getByText('LEGITIMATE FESTIVE SURGE')).toBeInTheDocument()
  expect(screen.getByText('LEGITIMATE FESTIVE SPIKE')).toBeInTheDocument()
  expect(screen.getByText('LIKELY FESTIVE')).toBeInTheDocument()
  expect(screen.getByText('MONITOR')).toBeInTheDocument()
  expect(screen.getByText('NO TIGHTEN_RULE')).toBeInTheDocument()
  expect(screen.getAllByText(/Coordinated abuse/i).length).toBeGreaterThan(0)
  expect(screen.getByText('SUSPICIOUS COORDINATED SPIKE')).toBeInTheDocument()
  expect(screen.getAllByText('COORDINATED ABUSE').length).toBeGreaterThan(0)
  expect(screen.getByText('TIGHTEN_RULE')).toBeInTheDocument()
  expect(screen.queryByText(/IEEE-CIS/)).not.toBeInTheDocument()
  expect(screen.getByText(HUMAN_APPROVAL_REQUIRED)).toBeInTheDocument()
  expect(screen.getByText(SIMULATION_ONLY)).toBeInTheDocument()
  expect(screen.getAllByText('Case #18').length).toBeGreaterThan(0)
  expect(screen.queryByText(FEST_ID)).not.toBeInTheDocument()
  expect(screen.queryByText(/money saved/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/live merchant traffic/i)).toBeInTheDocument()
})
