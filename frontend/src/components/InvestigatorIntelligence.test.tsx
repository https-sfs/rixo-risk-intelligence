import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { sampleIntelligence } from '../test/fixtures'
import { InvestigatorIntelligence } from './InvestigatorIntelligence'

test('renders structured investigator summary and operational false-positive wording', () => {
  render(<InvestigatorIntelligence intelligence={sampleIntelligence()} />)
  expect(screen.getByTestId('investigator-intelligence')).toBeInTheDocument()
  expect(screen.getByText('Investigator summary')).toBeInTheDocument()
  expect(screen.getByText('Why this case was flagged')).toBeInTheDocument()
  expect(screen.getByText('What supports the risk assessment')).toBeInTheDocument()
  expect(screen.getByText('What is actually observed')).toBeInTheDocument()
  expect(screen.getByText('What is derived')).toBeInTheDocument()
  expect(screen.getByText('What is uncertain / missing')).toBeInTheDocument()
  expect(screen.getByText('What the investigator should check next')).toBeInTheDocument()
  expect(screen.getByText('MODEL EVIDENCE: TRANSFERRED')).toBeInTheDocument()
  expect(screen.getByText(/not a fraud confirmation/)).toBeInTheDocument()
  expect(screen.getByText('Potential false-positive impact')).toBeInTheDocument()
  expect(screen.getByText(/Unnecessary human review/)).toBeInTheDocument()
  expect(screen.getByText(/No financial savings figure is available/)).toBeInTheDocument()
  expect(screen.getByText('Temporal breakdown')).toBeInTheDocument()
  expect(screen.getByText('Entity relationships')).toBeInTheDocument()
  expect(screen.getByText('Historical baseline')).toBeInTheDocument()
  expect(screen.queryByText(/₹/)).not.toBeInTheDocument()
  expect(screen.queryByText(/loss avoided/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/PROXY SIGNAL/)).not.toBeInTheDocument()
})

test('explains missing entity identifiers instead of inventing clusters', () => {
  render(
    <InvestigatorIntelligence
      intelligence={sampleIntelligence({
        entities: {
          available: false,
          missing: ['account', 'device', 'merchant'],
          note: 'This world does not contain identifiers that support entity clustering.',
        },
        temporal: { available: false, reason: 'Hourly history for this upload is unavailable.' },
        baseline: { available: false, reason: 'User-dataset hourly history was not retained for this session.' },
      })}
    />,
  )
  expect(
    screen.getByText('This world does not contain identifiers that support entity clustering.'),
  ).toBeInTheDocument()
  expect(screen.getByText(/Missing: account, device, merchant/)).toBeInTheDocument()
  expect(screen.getByText('Hourly history for this upload is unavailable.')).toBeInTheDocument()
  expect(
    screen.getByText('User-dataset hourly history was not retained for this session.'),
  ).toBeInTheDocument()
})

test('LIMITED status stays coverage-quality and is not a fraud verdict', () => {
  render(
    <InvestigatorIntelligence
      intelligence={sampleIntelligence({
        classifier_status: {
          status: 'LIMITED',
          headline: 'MODEL EVIDENCE: LIMITED',
          detail:
            'The shared IEEE-CIS classifier was applied outside its native training and evaluation world with low feature coverage. Scored-row count does not upgrade LIMITED coverage.',
          kind: 'evidence_quality',
          not_a_fraud_verdict: true,
          feature_coverage: 0.0139,
        },
      })}
    />,
  )
  expect(screen.getByText('MODEL EVIDENCE: LIMITED')).toBeInTheDocument()
  expect(screen.getByText(/does not upgrade LIMITED coverage/)).toBeInTheDocument()
  expect(screen.getByText(/not a fraud verdict/)).toBeInTheDocument()
  expect(screen.getByText(/does not authorize approval or simulation/)).toBeInTheDocument()
  expect(screen.queryByText(/fraud confirmed/i)).not.toBeInTheDocument()
})

test('does not render when intelligence is absent', () => {
  const { container } = render(<InvestigatorIntelligence intelligence={null} />)
  expect(container).toBeEmptyDOMElement()
})
