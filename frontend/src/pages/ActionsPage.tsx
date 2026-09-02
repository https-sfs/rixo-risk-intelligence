import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getAction, listAudit } from '../api/client'
import { HUMAN_APPROVAL_REQUIRED, SIMULATION_ONLY } from '../api/constants'
import { errorMessage, formatTimestamp } from '../api/format'
import { actionTypeLabel, friendlyCaseLabel, simulationSafetyCopy } from '../api/presentation'
import type { ActionState } from '../api/types'
import { EmptyState, ErrorState, LoadingState } from '../components/states'
import { StatusBadge } from '../components/StatusBadge'
import { useActionSession } from '../context/ActionSessionContext'

export function ActionsPage() {
  const { actionIds } = useActionSession()
  const [states, setStates] = useState<ActionState[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    listAudit({}, controller.signal)
      .then(async (audit) => {
        const fromAudit = audit.events.map((event) => event.action_id)
        const unique = [...new Set([...actionIds, ...fromAudit])]
        const loaded = await Promise.all(
          unique.map(async (id) => {
            try {
              return await getAction(id, controller.signal)
            } catch {
              return null
            }
          }),
        )
        if (!controller.signal.aborted) {
          setStates(loaded.filter((item): item is ActionState => item != null))
        }
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setError(errorMessage(err))
      })
    return () => controller.abort()
  }, [actionIds])

  if (error) return <ErrorState title="Actions unavailable" message={error} />
  if (!states) return <LoadingState label="Loading action state from the API…" />
  if (states.length === 0) {
    return (
      <div className="space-y-4">
        <Header />
        <EmptyState
          title="No actions in this session"
          message="Propose an action from an investigation. The API has no list-all-actions endpoint; this page reads audit events and known action IDs."
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Header />
      <p className="max-w-3xl text-sm text-mute">
        Governance is sequential: recommend → propose → {HUMAN_APPROVAL_REQUIRED} → simulate →
        verify. {SIMULATION_ONLY} — Razorpay TEST MODE only; no real money is moved.
      </p>
      <div className="table-wrap border border-line">
        <table className="w-full text-left text-sm">
          <thead className="bg-raised text-[11px] tracking-[0.12em] text-mute uppercase">
            <tr>
              <th className="px-3 py-2 font-medium">Action</th>
              <th className="px-3 py-2 font-medium">Spike</th>
              <th className="px-3 py-2 font-medium">Type</th>
              <th className="px-3 py-2 font-medium">Scope</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Approval</th>
              <th className="px-3 py-2 font-medium">Execution</th>
              <th className="px-3 py-2 font-medium">Verification</th>
            </tr>
          </thead>
          <tbody>
            {states.map((state) => {
              const verified =
                state.execution?.simulated === true || state.verification != null
              return (
                <tr key={state.proposal.action_id} className="border-t border-line align-top">
                  <td className="px-3 py-2 font-mono text-xs">{state.proposal.action_id}</td>
                  <td className="px-3 py-2 text-xs">
                    <Link className="text-brass hover:underline" to={`/investigations/${state.proposal.spike_id}`}>
                      {friendlyCaseLabel(state.proposal.spike_id, 'Case')}
                    </Link>
                  </td>
                  <td className="px-3 py-2">{actionTypeLabel(state.proposal.action_type)}</td>
                  <td className="px-3 py-2 text-mute">{state.proposal.scope}</td>
                  <td className="px-3 py-2">
                    <StatusBadge label={state.proposal.status} />
                  </td>
                  <td className="px-3 py-2">
                    {state.approval?.approved
                      ? `${state.approval.approved_by} · ${formatTimestamp(state.approval.approved_at)}`
                      : HUMAN_APPROVAL_REQUIRED}
                  </td>
                  <td className="px-3 py-2">
                    {state.execution?.simulated
                      ? `Simulation executed · ${simulationSafetyCopy(state.proposal.action_type).headline}`
                      : 'Not simulated'}
                  </td>
                  <td className="px-3 py-2">
                    {verified ? (
                      <StatusBadge label="Simulation recorded" tone="success" />
                    ) : (
                      <StatusBadge label="Pending" />
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Header() {
  return (
    <header>
      <p className="font-mono text-[11px] tracking-[0.2em] text-brass uppercase">
        {SIMULATION_ONLY}
      </p>
      <h1 className="mt-1 text-3xl font-semibold tracking-tight">Actions</h1>
      <p className="mt-2 text-sm text-mute">
        {HUMAN_APPROVAL_REQUIRED} before any simulation is recorded.
      </p>
    </header>
  )
}
