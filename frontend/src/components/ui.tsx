const LOOP = [
  'DETECT',
  'INVESTIGATE',
  'REASON',
  'DECIDE',
  'HUMAN APPROVAL',
  'EXECUTE',
  'AUDIT',
] as const
const GOVERNED = ['Decision', 'Approval', 'Simulation', 'Audit'] as const

function workflowStepClass(step: string): string {
  const key = step.trim().toUpperCase()
  if (key.includes('BLOCK') || key.includes('REJECT')) {
    return 'rixo-workflow-step rixo-workflow-step-blocked'
  }
  if (key.includes('APPROVED') || key === 'COMPLETED') {
    return 'rixo-workflow-step rixo-workflow-step-complete'
  }
  if (key.includes('APPROVAL') || key === 'ACT' || key === 'REVIEW') {
    return 'rixo-workflow-step rixo-workflow-step-review'
  }
  if (key.includes('EXECUTE') || key.includes('ACTION') || key.includes('SIMULATE')) {
    return 'rixo-workflow-step rixo-workflow-step-action'
  }
  return 'rixo-workflow-step'
}

export function WorkflowStrip({ steps }: { steps: string }) {
  const parts = steps.split(' → ')
  return (
    <p className="rixo-loop">
      <span className="sr-only">{steps}</span>
      {parts.map((step, index) => (
        <span key={`${step}-${index}`} className="inline-flex items-center gap-1" aria-hidden>
          <span className={workflowStepClass(step)}>{step}</span>
          {index < parts.length - 1 ? (
            <span className="rixo-loop-arrow">→</span>
          ) : null}
        </span>
      ))}
    </p>
  )
}

export function ProductLoop({
  label = 'RIXO operating loop',
}: {
  label?: string
}) {
  return (
    <div aria-label={label}>
      <WorkflowStrip steps={LOOP.join(' → ')} />
    </div>
  )
}

export function GovernedLoop() {
  return (
    <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4" aria-label="Governed action stages">
      {GOVERNED.map((step, index) => (
        <li
          key={step}
          className="rounded-[10px] border border-line bg-panel px-3 py-2 text-center text-[11px] font-semibold tracking-[0.08em] uppercase"
        >
          <span className="text-brass">{index + 1}</span>
          <span className="mt-0.5 block text-ink">{step}</span>
        </li>
      ))}
    </ol>
  )
}

export function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-start gap-3">
      <span className="mt-1.5 h-8 w-1 shrink-0 bg-brass" aria-hidden />
      <div>
        <p className="font-display text-2xl font-semibold tracking-tight text-navy">
          RIXO
        </p>
        {compact ? null : (
          <p className="mt-1 text-xs leading-snug text-mute">
            Risk Intelligence &amp; eXecution Operations
          </p>
        )}
      </div>
    </div>
  )
}
