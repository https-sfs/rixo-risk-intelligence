import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { ClassifierPanel } from './ClassifierPanel'

test('renders scored classifier evidence', () => {
  render(
    <ClassifierPanel
      classifier={{
        status: 'scored',
        fraud_risk_score: 0.87,
        classification: 'High risk',
        model: 'ieee_hgb',
        model_version: 2,
        feature_coverage: 0.92,
      }}
    />,
  )
  expect(screen.getByText('Classifier evidence')).toBeInTheDocument()
  expect(screen.getByText(/Supporting evidence from the shared classifier/)).toBeInTheDocument()
  expect(screen.getByText('0.87')).toBeInTheDocument()
  expect(screen.getByText('High risk')).toBeInTheDocument()
  expect(screen.getByText(/ieee_hgb/)).toBeInTheDocument()
  expect(screen.getByText('92.00%')).toBeInTheDocument()
})

test('renders not-scored status without fabricating a score', () => {
  render(
    <ClassifierPanel
      classifier={{
        status: 'not_scored',
        reason: 'Required feature(s) unavailable',
        missing_features: ['TransactionAmt', 'TransactionDT'],
      }}
    />,
  )
  expect(screen.getByText('Not scored')).toBeInTheDocument()
  expect(screen.getByText('Required feature(s) unavailable')).toBeInTheDocument()
  expect(screen.getByText(/TransactionAmt, TransactionDT/)).toBeInTheDocument()
  expect(screen.queryByText(/IEEE-CIS model was not applied/)).not.toBeInTheDocument()
})

test('in-sample overlay cannot be read as test or production performance', () => {
  render(
    <ClassifierPanel
      classifier={{
        status: 'scored',
        fraud_risk_score: 0.68,
        classification: 'High risk',
        model: 'ieee_hgb',
        sample_scope: 'IN_SAMPLE_MODEL_OVERLAY',
      }}
    />,
  )
  expect(screen.getByText(/IN_SAMPLE_MODEL_OVERLAY/)).toBeInTheDocument()
  expect(screen.getByText(/not held-out test performance/)).toBeInTheDocument()
  expect(screen.getByText(/not model accuracy/)).toBeInTheDocument()
  expect(screen.getByText(/not production performance/)).toBeInTheDocument()
})
