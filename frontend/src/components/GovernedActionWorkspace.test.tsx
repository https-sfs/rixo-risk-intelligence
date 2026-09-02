import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { expect, test, vi } from 'vitest'
import { formatTimestamp } from '../api/format'
import { GovernedActionWorkspace } from './GovernedActionWorkspace'

const BASE = {
  actionType: 'flag_for_human_review',
  anomalyKind: 'Amount-concentration anomaly',
  periodLabel: '20 Jan 2026 · 9:00 PM',
  transactionCount: 76,
  amountLabel: '58,325.33',
  fraudLabelCount: 1,
  busy: null as string | null,
  actionError: null as string | null,
  onPropose: vi.fn(),
  onApprove: vi.fn(),
  onSimulate: vi.fn(),
  caseId: 'cda-20260120-21',
}

const AUDIT = [
  {
    kind: 'CUSTOM_DECISION_RECORDED',
    timestamp: '2026-09-01T14:07:42+00:00',
    audit_event_id: 'e1',
  },
  {
    kind: 'CUSTOM_ACTION_PROPOSED',
    timestamp: '2026-09-01T14:07:42+00:00',
    audit_event_id: 'e2',
  },
  {
    kind: 'CUSTOM_ACTION_APPROVED',
    timestamp: '2026-09-01T14:07:42+00:00',
    audit_event_id: 'e3',
  },
  {
    kind: 'CUSTOM_ACTION_SIMULATED',
    timestamp: '2026-09-01T14:08:00+00:00',
    audit_event_id: 'e4',
  },
]

function renderWorkspace(
  overrides: Partial<ComponentProps<typeof GovernedActionWorkspace>> = {},
) {
  return render(
    <GovernedActionWorkspace
      {...BASE}
      proposal={null}
      approval={null}
      execution={null}
      audit={[]}
      {...overrides}
    />,
  )
}

test('four tabs show materially different content from live state', async () => {
  const user = userEvent.setup()
  renderWorkspace()

  const decide = screen.getByRole('tabpanel')
  expect(within(decide).getByText('Decision')).toBeInTheDocument()
  expect(within(decide).getByText(/flag for human review/i)).toBeInTheDocument()
  expect(within(decide).getByText(/76 transactions/)).toBeInTheDocument()
  expect(within(decide).getByText(/Total observed amount: 58,325.33/)).toBeInTheDocument()
  expect(within(decide).getByText(/warrants human investigation/)).toBeInTheDocument()
  expect(within(decide).queryByText('Approval required')).not.toBeInTheDocument()
  expect(within(decide).queryByText('NOT SIMULATED')).not.toBeInTheDocument()
  expect(within(decide).queryByText('Audit history')).not.toBeInTheDocument()
  expect(screen.queryByText('cda-20260120-21')).not.toBeInTheDocument()

  await user.click(screen.getByRole('tab', { name: 'Approval' }))
  const approval = screen.getByRole('tabpanel')
  expect(within(approval).getByText('Approval required')).toBeInTheDocument()
  expect(within(approval).getByText('YES')).toBeInTheDocument()
  expect(within(approval).getByText('Flag this anomaly for human review')).toBeInTheDocument()
  expect(within(approval).getByText('PENDING')).toBeInTheDocument()
  expect(within(approval).queryByText(/warrants human investigation/)).not.toBeInTheDocument()
  expect(within(approval).queryByText(/76 transactions/)).not.toBeInTheDocument()
  expect(within(approval).queryByText('NOT SIMULATED')).not.toBeInTheDocument()

  await user.click(screen.getByRole('tab', { name: 'Simulation' }))
  const simulate = screen.getByRole('tabpanel')
  expect(within(simulate).getByText('Simulation')).toBeInTheDocument()
  expect(within(simulate).getByText(/placed into a human-review queue/)).toBeInTheDocument()
  expect(within(simulate).getByText('Simulation impact')).toBeInTheDocument()
  expect(
    within(simulate).getByText(
      /demonstrates the action that would be taken in a production fraud-response environment/,
    ),
  ).toBeInTheDocument()
  expect(
    within(simulate).getByText('Payment: Would block the flagged payment in a live deployment.'),
  ).toBeInTheDocument()
  expect(
    within(simulate).getByText(
      'Merchant account: Would apply the approved merchant-account action in a live deployment.',
    ),
  ).toBeInTheDocument()
  expect(
    within(simulate).getByText('Execution: Simulated only — no live payment is executed.'),
  ).toBeInTheDocument()
  expect(
    within(simulate).getByText('Money movement: Simulated only — no real money is moved.'),
  ).toBeInTheDocument()
  expect(within(simulate).queryByText('No payment would be blocked')).not.toBeInTheDocument()
  expect(within(simulate).getByText('NOT SIMULATED')).toBeInTheDocument()
  expect(within(simulate).queryByText('Approval required')).not.toBeInTheDocument()
  expect(within(simulate).queryByText(/warrants human investigation/)).not.toBeInTheDocument()
  expect(within(simulate).queryByText('Audit history')).not.toBeInTheDocument()

  await user.click(screen.getByRole('tab', { name: 'Audit history' }))
  const audit = screen.getByRole('tabpanel')
  expect(within(audit).getByText('No audit events have been recorded yet.')).toBeInTheDocument()
  expect(within(audit).queryByText(/human-review queue/)).not.toBeInTheDocument()
  expect(within(audit).queryByText('PENDING')).not.toBeInTheDocument()
  expect(within(audit).queryByText(/76 transactions/)).not.toBeInTheDocument()
})

test('approval and simulation status follow the recorded state', async () => {
  const user = userEvent.setup()
  const { rerender } = renderWorkspace({
    proposal: { action_id: 'a1', action_type: 'flag_for_human_review' },
  })

  await user.click(screen.getByRole('tab', { name: 'Approval' }))
  expect(screen.getByText('PENDING')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument()

  rerender(
    <GovernedActionWorkspace
      {...BASE}
      proposal={{ action_id: 'a1', action_type: 'flag_for_human_review' }}
      approval={{ approved: true, approved_at: '2026-09-01T14:07:42+00:00' }}
      execution={null}
      audit={AUDIT.slice(0, 3)}
    />,
  )
  await user.click(screen.getByRole('tab', { name: 'Approval' }))
  expect(screen.getByText('APPROVED')).toBeInTheDocument()
  expect(screen.getByText('Approval recorded')).toBeInTheDocument()
  expect(screen.getByText(formatTimestamp('2026-09-01T14:07:42+00:00'))).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()

  await user.click(screen.getByRole('tab', { name: 'Simulation' }))
  expect(screen.getByText('NOT SIMULATED')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Run dry-run simulation' })).toBeInTheDocument()

  rerender(
    <GovernedActionWorkspace
      {...BASE}
      proposal={{ action_id: 'a1', action_type: 'flag_for_human_review' }}
      approval={{ approved: true, approved_at: '2026-09-01T14:07:42+00:00' }}
      execution={{ simulated: true, action_type: 'flag_for_human_review' }}
      audit={AUDIT}
    />,
  )
  await user.click(screen.getByRole('tab', { name: 'Simulation' }))
  expect(screen.getByText('SIMULATION COMPLETED')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Run dry-run simulation' })).not.toBeInTheDocument()
})

test('audit tab is a human-readable timeline and keeps codes in technical details', async () => {
  const user = userEvent.setup()
  renderWorkspace({
    proposal: { action_id: 'a1', action_type: 'flag_for_human_review' },
    approval: { approved: true, approved_at: '2026-09-01T14:07:42+00:00' },
    execution: { simulated: true },
    audit: AUDIT,
  })

  await user.click(screen.getByRole('tab', { name: 'Audit history' }))
  const panel = screen.getByRole('tabpanel')
  expect(within(panel).getByText('Decision recorded')).toBeInTheDocument()
  expect(within(panel).getByText('Action proposed')).toBeInTheDocument()
  expect(within(panel).getByText('Approval recorded')).toBeInTheDocument()
  expect(within(panel).getByText('Simulation completed')).toBeInTheDocument()
  expect(within(panel).getByText('System decision: Flag for human review')).toBeInTheDocument()
  const timeline = panel.querySelector('ol')
  expect(timeline).not.toBeNull()
  expect(within(timeline as HTMLElement).getAllByText(formatTimestamp('2026-09-01T14:07:42+00:00')).length).toBeGreaterThan(0)
  expect(within(timeline as HTMLElement).queryByText('2026-09-01T14:07:42+00:00')).not.toBeInTheDocument()

  const details = panel.querySelector('details')
  expect(details).not.toBeNull()
  expect(within(details as HTMLElement).getByText(/CUSTOM_DECISION_RECORDED/)).toBeInTheDocument()
  expect(within(details as HTMLElement).getByText(/Technical anomaly ID: cda-20260120-21/)).toBeInTheDocument()
  expect(within(details as HTMLElement).getAllByText(/2026-09-01T14:07:42\+00:00/).length).toBeGreaterThan(0)
  expect(within(timeline as HTMLElement).queryByText('flag_for_human_review')).not.toBeInTheDocument()
  expect(within(panel).queryByRole('link', { name: '← Back to anomalies' })).not.toBeInTheDocument()
})

test('simulation tab distinguishes internal and Razorpay TEST results', async () => {
  const user = userEvent.setup()
  renderWorkspace({
    proposal: { action_id: 'a1', action_type: 'flag_for_human_review' },
    approval: { approved: true, approved_at: '2026-09-01T14:07:42+00:00' },
    execution: {
      simulated: true,
      razorpay_test: {
        status: 'completed',
        provider: 'razorpay',
        environment: 'test',
        message: 'Razorpay test simulation completed.',
        test_order_id: 'order_test_abc',
      },
    },
    audit: [
      ...AUDIT,
      {
        kind: 'CUSTOM_RAZORPAY_TEST_SIMULATED',
        timestamp: '2026-09-01T14:08:05+00:00',
        audit_event_id: 'e5',
      },
    ],
  })

  expect(screen.getAllByText(/TEST MODE ONLY/).length).toBeGreaterThan(0)
  expect(screen.getAllByText(/No real money is moved/).length).toBeGreaterThan(0)
  expect(screen.getAllByText(/Human approval is required/).length).toBeGreaterThan(0)
  expect(screen.queryByText(/No Razorpay API/)).not.toBeInTheDocument()

  await user.click(screen.getByRole('tab', { name: 'Simulation' }))
  expect(screen.getByText('Internal simulation')).toBeInTheDocument()
  expect(screen.getByText('Razorpay TEST simulation')).toBeInTheDocument()
  expect(screen.getByText('Razorpay test simulation')).toBeInTheDocument()
  expect(
    screen.getByText(
      'Demonstrates the corresponding payment-system operation using Razorpay Test Mode. No real payment or money movement occurs.',
    ),
  ).toBeInTheDocument()
  expect(screen.getByText(/Test order: order_test_abc/)).toBeInTheDocument()
  expect(screen.queryByText(/Payment executed/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/payment was blocked/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/merchant account was actually changed/i)).not.toBeInTheDocument()

  await user.click(screen.getByRole('tab', { name: 'Audit history' }))
  expect(screen.getByText('Razorpay test simulation completed')).toBeInTheDocument()
})

test('simulation requires approval and shows Razorpay configuration-missing and failure states', async () => {
  const user = userEvent.setup()
  const { rerender } = renderWorkspace({
    proposal: { action_id: 'a1', action_type: 'flag_for_human_review' },
    approval: null,
    execution: null,
  })

  await user.click(screen.getByRole('tab', { name: 'Simulation' }))
  expect(screen.getByText(/Human approval is required before this dry-run/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Run dry-run simulation' })).not.toBeInTheDocument()

  rerender(
    <GovernedActionWorkspace
      {...BASE}
      proposal={{ action_id: 'a1', action_type: 'flag_for_human_review' }}
      approval={{ approved: true, approved_at: '2026-09-01T14:07:42+00:00' }}
      execution={{
        simulated: true,
        razorpay_test: {
          status: 'unavailable',
          message: 'Razorpay test integration is unavailable (configuration missing).',
        },
      }}
      audit={AUDIT}
    />,
  )
  await user.click(screen.getByRole('tab', { name: 'Simulation' }))
  expect(screen.getByText('Unavailable — configuration missing')).toBeInTheDocument()
  expect(screen.getByText('SIMULATION COMPLETED')).toBeInTheDocument()

  rerender(
    <GovernedActionWorkspace
      {...BASE}
      proposal={{ action_id: 'a1', action_type: 'flag_for_human_review' }}
      approval={{ approved: true, approved_at: '2026-09-01T14:07:42+00:00' }}
      execution={{
        simulated: false,
        razorpay_test: {
          status: 'failed',
          message: 'Razorpay TEST request was rejected (HTTP 502).',
        },
      }}
      audit={[
        ...AUDIT.slice(0, 3),
        {
          kind: 'CUSTOM_RAZORPAY_TEST_FAILED',
          timestamp: '2026-09-01T14:08:05+00:00',
          audit_event_id: 'e5',
        },
      ]}
    />,
  )
  await user.click(screen.getByRole('tab', { name: 'Simulation' }))
  expect(screen.getByText('Failed')).toBeInTheDocument()
  expect(screen.getByText('NOT SIMULATED')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Run dry-run simulation' })).toBeInTheDocument()
})

test('recorded investigation state does not offer the decision again', async () => {
  const user = userEvent.setup()
  renderWorkspace({
    decision: { anomaly_id: 'cda-a', recorded_at: '2026-09-01T14:07:42+00:00' },
    proposal: { action_id: 'a1', action_type: 'flag_for_human_review', created_at: '2026-09-01T14:07:42+00:00' },
    approval: { approved: true, approved_at: '2026-09-01T14:07:42+00:00' },
    execution: { simulated: true },
    audit: AUDIT,
  })

  await user.click(screen.getByRole('tab', { name: 'Decision' }))
  expect(screen.queryByRole('button', { name: 'Record this decision' })).not.toBeInTheDocument()
  expect(screen.getByText('Decision recorded')).toBeInTheDocument()
})
