import type { InvestigationAgentResult } from '../api/types'

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

export function InvestigationAgent({
  agent,
}: {
  agent?: InvestigationAgentResult | null
}) {
  if (!agent) return null
  const supporting = agent.supporting_evidence ?? []
  const contradictory = agent.contradictory_evidence ?? []
  const uncertainty = agent.uncertainty ?? []
  const trace = agent.trace ?? []

  return (
    <section className="border border-line bg-panel p-5" data-testid="investigation-agent">
      <h2 className="text-lg font-semibold">Investigation agent</h2>
      <p className="mt-1 text-xs text-mute">
        Bounded read-only investigation using available case evidence. It does not make or
        execute governance decisions.
      </p>
      {agent.finding ? (
        <div className="mt-4">
          <h3 className="text-[11px] tracking-[0.14em] text-mute uppercase">Investigator finding</h3>
          <p className="mt-2 text-sm">{agent.finding}</p>
        </div>
      ) : null}
      {supporting.length > 0 ? (
        <div className="mt-4">
          <h3 className="text-[11px] tracking-[0.14em] text-mute uppercase">Evidence inspected</h3>
          <ul className="mt-2 list-disc space-y-1 pl-4 text-sm">
            {supporting.map((item) => (
              <li key={`${item.tool}-${item.statement}`}>
                {item.statement}
                {item.provenance ? (
                  <span className="text-mute"> · {asString(item.provenance)}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {contradictory.length > 0 ? (
        <div className="mt-4">
          <h3 className="text-[11px] tracking-[0.14em] text-mute uppercase">Uncertainty / limits</h3>
          <ul className="mt-2 list-disc space-y-1 pl-4 text-sm">
            {contradictory.map((item) => (
              <li key={`${item.tool}-${item.statement}`}>{item.statement}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {uncertainty.length > 0 ? (
        <div className="mt-4">
          <h3 className="text-[11px] tracking-[0.14em] text-mute uppercase">Classifier and coverage limits</h3>
          <ul className="mt-2 list-disc space-y-1 pl-4 text-sm">
            {uncertainty.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {agent.recommended_next_human_check ? (
        <div className="mt-4">
          <h3 className="text-[11px] tracking-[0.14em] text-mute uppercase">
            Recommended next human check
          </h3>
          <p className="mt-2 text-sm">{agent.recommended_next_human_check}</p>
        </div>
      ) : null}
      {trace.length > 0 ? (
        <div className="mt-4">
          <h3 className="text-[11px] tracking-[0.14em] text-mute uppercase">Investigator trace</h3>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm">
            {trace.map((step) => (
              <li key={step.tool}>
                {asString(step.label || step.tool).replace(/_/g, ' ')}
                {step.status === 'completed' ? ' · completed' : ''}
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </section>
  )
}
