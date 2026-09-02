import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { AuditPage } from './AuditPage'
import { installApiMock } from '../test/mockApi'

afterEach(() => {
  vi.unstubAllGlobals()
})

test('audit page is labeled as a simulation audit trail', async () => {
  installApiMock()
  render(
    <MemoryRouter>
      <AuditPage />
    </MemoryRouter>,
  )
  expect(await screen.findByRole('heading', { name: 'Audit' })).toBeInTheDocument()
  expect(screen.getByText('SIMULATION AUDIT TRAIL')).toBeInTheDocument()
  expect(screen.getByText(/Decision recorded/)).toBeInTheDocument()
  expect(screen.getByText(/Action proposed/)).toBeInTheDocument()
  expect(screen.getByText(/Approval recorded/)).toBeInTheDocument()
  expect(screen.getByText(/Simulation completed/)).toBeInTheDocument()
  expect(screen.getByText(/Simulation verified/)).toBeInTheDocument()
  expect(screen.getByText(/Razorpay test simulation completed or failed/)).toBeInTheDocument()
  expect(screen.getByText(/Technical event codes belong under Technical audit details/)).toBeInTheDocument()
  expect(screen.getByText(/not a production payment audit/i)).toBeInTheDocument()
})
