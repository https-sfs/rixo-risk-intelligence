import { formatTechnicalTimestamp, formatTimestamp } from '../api/format'
import { auditEventLabel, auditEventNarrative } from '../api/presentation'

export type AuditEventLike = Record<string, unknown>

function eventKind(event: AuditEventLike): string {
  return String(event.kind ?? event.event_type ?? '')
}

function eventId(event: AuditEventLike): string {
  return String(event.audit_event_id ?? event.event_id ?? `${eventKind(event)}-${event.timestamp ?? ''}`)
}

function eventTimestamp(event: AuditEventLike): string {
  return typeof event.timestamp === 'string' ? event.timestamp : String(event.timestamp ?? '')
}

export function AuditPanel({
  events,
  actionType,
  caseId,
  caseIdLabel = 'Technical anomaly ID',
  extraTechnical = [],
}: {
  events: AuditEventLike[]
  actionType?: string | null
  simulated?: boolean
  caseId?: string | null
  caseIdLabel?: string
  extraTechnical?: Array<{ label: string; value: string | null | undefined }>
}) {
  if (events.length === 0) return null

  return (
    <section className="border border-line bg-panel p-5">
      <h2 className="text-lg font-semibold">Audit</h2>
      <ol className="mt-4 space-y-3 text-sm">
        {events.map((event) => {
          const kind = eventKind(event)
          const narrative = auditEventNarrative(kind, actionType)
          return (
            <li key={eventId(event)} className="border-t border-line pt-3 first:border-0 first:pt-0">
              <p className="font-semibold">{auditEventLabel(kind)}</p>
              <p className="mt-1 text-mute">{formatTimestamp(eventTimestamp(event))}</p>
              {narrative ? <p className="mt-1">{narrative}</p> : null}
            </li>
          )
        })}
      </ol>
      <details className="mt-5 border border-line bg-raised/40 px-3 py-2">
        <summary className="cursor-pointer text-sm font-medium">Technical details</summary>
        <ul className="mt-3 space-y-2 font-mono text-xs text-mute">
          {caseId ? (
            <li>
              {caseIdLabel}: {caseId}
            </li>
          ) : null}
          {extraTechnical.map((row) =>
            row.value ? (
              <li key={row.label}>
                {row.label}: {row.value}
              </li>
            ) : null,
          )}
          {events.map((event) => (
            <li key={`${eventId(event)}-tech`} className="border-t border-line pt-2">
              <p>Event code: {eventKind(event)}</p>
              <p>UTC timestamp: {formatTechnicalTimestamp(eventTimestamp(event))}</p>
            </li>
          ))}
        </ul>
      </details>
    </section>
  )
}
