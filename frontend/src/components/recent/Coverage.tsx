import { ZENODO_RECENT_URL } from '../../api/constants'

type Kind = 'observed' | 'derived' | 'proxy' | 'truth' | 'source'

const KIND_CLASS: Record<Kind, string> = {
  observed: 'border-line bg-raised text-ink',
  derived: 'border-line bg-raised text-ink',
  proxy: 'border-brass/40 bg-brass/10 text-brass',
  truth: 'border-line bg-panel text-mute',
  source: 'border-line bg-raised text-mute',
}

export function SignalKindBadge({ kind }: { kind: Kind }) {
  const label =
    kind === 'observed'
      ? 'Observed'
      : kind === 'derived'
        ? 'Derived'
        : kind === 'proxy'
          ? 'Proxy'
          : kind === 'truth'
            ? 'Delayed ground truth'
            : 'Source dataset model output'
  return (
    <span
      className={`inline-flex items-center border px-1.5 py-0.5 text-[10px] font-semibold tracking-[0.12em] uppercase ${KIND_CLASS[kind]}`}
    >
      {label}
    </span>
  )
}

export function EvidenceCoverage() {
  return (
    <section className="border border-line bg-panel px-4 py-4">
      <h2 className="text-lg font-semibold">Evidence coverage</h2>
      <p className="mt-1 text-sm text-mute">
        Signals this investigation can use from the January 2026 collection, and families the
        export does not contain.
      </p>
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <CoverageGroup title="Observed signals" kind="observed">
          Transaction volume, transaction amount (USD), calendar timestamps, transaction IDs
        </CoverageGroup>
        <CoverageGroup title="Proxy signals" kind="proxy">
          IP address as supplied. January IPs are unique per row, so they do not support
          repeat-entity concentration.
        </CoverageGroup>
        <CoverageGroup title="Unavailable signal families" kind="source">
          Account, device, merchant, SKU, payment outcome, and source inference latency
        </CoverageGroup>
      </div>
    </section>
  )
}

function CoverageGroup({
  title,
  kind,
  children,
}: {
  title: string
  kind: Kind
  children: string
}) {
  return (
    <div>
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        <SignalKindBadge kind={kind} />
      </div>
      <p className="mt-2 text-sm text-mute">{children}</p>
    </div>
  )
}

export function DatasetLimitations() {
  return (
    <details className="border border-line bg-panel px-4 py-3">
      <summary className="cursor-pointer text-sm font-semibold">
        Dataset methodology & limitations
      </summary>
      <div className="mt-3 space-y-3 text-sm text-mute">
        <p>
          Recent public online-banking transaction data collected in January 2026. Historical
          labels are used only for evaluation. This is not our live production traffic.
        </p>
        <p>
          <span className="text-ink">Observed</span> fields come from the export.{' '}
          <span className="text-ink">Derived</span> hour buckets are floored from{' '}
          <code>timestamp</code>. <span className="text-ink">Proxy</span> IP addresses are not
          verified customer identities.{' '}
          <span className="text-ink">Delayed ground truth</span> is <code>is_fraud</code>, used
          only as an overlay. Source CNN-LSTM probability, risk, confidence, and recommendation
          are <span className="text-ink">source dataset model outputs</span> and are never our
          scores.
        </p>
        <p>
          Account, device, merchant, SKU, and payment-status fields are absent. Primary metrics
          use the January collection (rows with <code>test_date</code>). Extra export rows without
          that date are excluded.
        </p>
        <p>
          Source:{' '}
          <a className="text-brass hover:underline" href={ZENODO_RECENT_URL}>
            Zenodo record 20359708
          </a>
          . Licence CC BY 4.0.
        </p>
        <p>
          This public dataset is used for historical evaluation and validation of the
          investigation pipeline; it is not a live production traffic feed.
        </p>
        <p>
          Labelled fraud value is historical ground truth, not money saved/prevented.
        </p>
        <p>
          Source-model outputs are external evidence from the source dataset, not scores from
          this system.
        </p>
      </div>
    </details>
  )
}
