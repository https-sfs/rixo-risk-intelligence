import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'
import { ActionSessionProvider } from '../context/ActionSessionContext'
import { ApiStatusProvider } from '../context/ApiStatusContext'
import { CustomUploadPage } from './CustomUploadPage'
import { installApiMock } from '../test/mockApi'

afterEach(() => {
  vi.unstubAllGlobals()
})

test('bring your data is a first-class upload workspace', async () => {
  installApiMock()
  render(
    <MemoryRouter>
      <ApiStatusProvider>
        <ActionSessionProvider>
          <CustomUploadPage />
        </ActionSessionProvider>
      </ApiStatusProvider>
    </MemoryRouter>,
  )
  expect(screen.getByText('BRING YOUR DATA')).toBeInTheDocument()
  expect(screen.getByText('Your transactions. Our investigation engine.')).toBeInTheDocument()
  expect(screen.getByText(/Test the Fraud-Spike Investigator on your own transaction history/)).toBeInTheDocument()
  expect(screen.getByText('Upload CSV')).toBeInTheDocument()
  expect(screen.getByText(/Minimum useful fields/)).toBeInTheDocument()
  expect(screen.getByText(/transaction ID, amount, timestamp/)).toBeInTheDocument()
  expect(screen.getByText(/not mixed with Synthetic Demo, IEEE-CIS, or January 2026/)).toBeInTheDocument()
  expect(await screen.findByText(/Maximum file size: 1 GB/)).toBeInTheDocument()
  expect(screen.getByText(/Maximum rows: 2,000,000/)).toBeInTheDocument()
  expect(screen.queryByText(/money saved/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/Razorpay payment API/)).not.toBeInTheDocument()
})

test('rejects a selected file over 1 GB before starting upload', async () => {
  installApiMock()
  render(
    <MemoryRouter>
      <ApiStatusProvider>
        <ActionSessionProvider>
          <CustomUploadPage />
        </ActionSessionProvider>
      </ApiStatusProvider>
    </MemoryRouter>,
  )
  expect(await screen.findByText(/Maximum file size: 1 GB/)).toBeInTheDocument()
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  const file = new File(['transaction_id,amount,timestamp\n1,2,2026-01-01\n'], 'huge.csv', {
    type: 'text/csv',
  })
  Object.defineProperty(file, 'size', { value: 1024 * 1024 * 1024 + 1 })
  fireEvent.change(input, { target: { files: [file] } })
  expect(await screen.findByText(/Upload rejected: file is/)).toBeInTheDocument()
  expect(screen.queryByText(/Uploading/)).not.toBeInTheDocument()
})

test('shows identified fields after upload and keeps the mapping table behind review', async () => {
  const user = userEvent.setup()
  installApiMock()
  render(
    <MemoryRouter>
      <ApiStatusProvider>
        <ActionSessionProvider>
          <CustomUploadPage />
        </ActionSessionProvider>
      </ApiStatusProvider>
    </MemoryRouter>,
  )
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  const file = new File(['transaction_id,amount,timestamp\n1,2,2026-01-01\n'], 'merchant.csv', {
    type: 'text/csv',
  })
  fireEvent.change(input, { target: { files: [file] } })
  expect(await screen.findByText('Fields identified')).toBeInTheDocument()
  expect(screen.getByText(/3\/5 required fields identified automatically/)).toBeInTheDocument()
  expect(screen.getByText(/Transaction ID/)).toBeInTheDocument()
  expect(screen.queryByText('Review mappings')).toBeInTheDocument()
  expect(screen.queryByText('Your column')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Review mappings' }))
  expect(screen.getByText('Your column')).toBeInTheDocument()
})
