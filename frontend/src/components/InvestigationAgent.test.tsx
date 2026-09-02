import { render, screen, within } from '@testing-library/react'
import { expect, test } from 'vitest'
import { sampleAgent } from '../test/fixtures'
import { InvestigationAgent } from './InvestigationAgent'

test('renders investigator finding, provenance, and tool trace', () => {
  render(<InvestigationAgent agent={sampleAgent()} />)
  const section = screen.getByTestId('investigation-agent')
  expect(section).toBeInTheDocument()
  expect(screen.getByText('Investigation agent')).toBeInTheDocument()
  expect(
    screen.getByText(
      /Bounded read-only investigation using available case evidence. It does not make or execute governance decisions./,
    ),
  ).toBeInTheDocument()
  expect(screen.getByText('Investigator finding')).toBeInTheDocument()
  expect(screen.getByText('Detector type: suspicious_coordinated_spike.')).toBeInTheDocument()
  expect(screen.getByText('Evidence inspected')).toBeInTheDocument()
  expect(screen.getByText(/Window volume: 75 transactions/)).toBeInTheDocument()
  expect(screen.getAllByText(/· OBSERVED/).length).toBeGreaterThan(0)
  expect(screen.getByText('Investigator trace')).toBeInTheDocument()
  expect(screen.getByText(/inspect case metrics · completed/)).toBeInTheDocument()
  expect(screen.getByText(/inspect classifier evidence · completed/)).toBeInTheDocument()
  expect(screen.getByText(/supporting evidence only/)).toBeInTheDocument()
  expect(screen.getByText('Recommended next human check')).toBeInTheDocument()
  expect(within(section).queryByRole('textbox')).not.toBeInTheDocument()
  expect(within(section).queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
  expect(within(section).queryByRole('button', { name: 'Run dry-run simulation' })).not.toBeInTheDocument()
  expect(within(section).queryByText(/confirmed fraud/i)).not.toBeInTheDocument()
  expect(within(section).queryByText(/Ask AI/i)).not.toBeInTheDocument()
})

test('renders unavailable evidence without inventing identifiers', () => {
  render(
    <InvestigationAgent
      agent={sampleAgent({
        world: 'RECENT PUBLIC DATA',
        finding: 'January anomaly at the selected hour.',
        supporting_evidence: [
          { statement: '10 transactions.', tool: 'inspect_case_metrics', provenance: 'OBSERVED' },
        ],
        contradictory_evidence: [
          {
            statement: 'This world does not contain identifiers that support entity clustering.',
            tool: 'inspect_entities',
            provenance: 'OBSERVED',
          },
        ],
        uncertainty: [
          'MODEL EVIDENCE: LIMITED — supporting evidence only. Not a fraud confirmation and not an action authorization.',
          'Unavailable identifiers: account, device, merchant, SKU.',
        ],
      })}
    />,
  )
  expect(
    screen.getByText('This world does not contain identifiers that support entity clustering.'),
  ).toBeInTheDocument()
  expect(screen.getByText(/Unavailable identifiers: account, device, merchant, SKU/)).toBeInTheDocument()
  expect(screen.queryByText(/dev_/)).not.toBeInTheDocument()
  expect(screen.queryByText(/confirmed fraud/i)).not.toBeInTheDocument()
})

test('classifier wording stays supporting evidence', () => {
  render(
    <InvestigationAgent
      agent={sampleAgent({
        finding: 'Detector type: legitimate_festive_spike.',
        uncertainty: [
          'MODEL EVIDENCE: LIMITED — supporting evidence only. Not a fraud confirmation and not an action authorization.',
        ],
      })}
    />,
  )
  expect(screen.getByText(/MODEL EVIDENCE: LIMITED/)).toBeInTheDocument()
  expect(screen.getByText(/supporting evidence only/)).toBeInTheDocument()
  expect(screen.queryByText(/classifier detected/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/confirms fraud/i)).not.toBeInTheDocument()
})

test('does not render when the agent payload is absent', () => {
  const { container } = render(<InvestigationAgent agent={null} />)
  expect(container).toBeEmptyDOMElement()
})
