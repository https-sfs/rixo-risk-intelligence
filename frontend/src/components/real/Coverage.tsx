type Kind = 'observed' | 'derived' | 'proxy' | 'truth' | 'boundary' | 'model'

const KIND_CLASS: Record<Kind, string> = {
  observed: 'border-line bg-raised text-ink',
  derived: 'border-line bg-raised text-ink',
  proxy: 'border-brass/40 bg-brass/10 text-brass',
  truth: 'border-line bg-panel text-mute',
  boundary: 'border-line bg-raised text-mute',
  model: 'border-brass/40 bg-brass/10 text-brass',
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
            : kind === 'model'
              ? 'Model prediction'
              : 'Outside dataset'
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
        What this investigation can use from IEEE-CIS, and what the dataset does not contain.
      </p>
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <CoverageGroup title="Observed signals" kind="observed">
          Transaction volume, transaction amount
        </CoverageGroup>
        <CoverageGroup title="Derived signals" kind="derived">
          ProductCD share, relative-hour detector score
        </CoverageGroup>
        <CoverageGroup title="Proxy signals" kind="proxy">
          Card fields, address fields, DeviceType / DeviceInfo, identity-join coverage
        </CoverageGroup>
        <CoverageGroup title="Unavailable signal families" kind="boundary">
          Network identity, payment outcome, exact product/SKU, calendar/festive context,
          coordinated-abuse ground truth
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
        Dataset limitations & methodology
      </summary>
      <div className="mt-3 space-y-3 text-sm text-mute">
        <p>
          IEEE-CIS provides elapsed transaction time rather than calendar timestamps. Relative
          hour buckets order events; they are not dates, weekdays, or festive periods.
        </p>
        <p>
          <span className="text-ink">Observed</span> fields are present in the public tables.{' '}
          <span className="text-ink">Derived</span> values are computed from those fields
          (ProductCD share, detector hour score).{' '}
          <span className="text-ink">Proxy</span> fields are masked or joined substitutes, not
          true account/device/SKU identities.{' '}
          <span className="text-ink">Delayed ground truth</span> is <code>isFraud</code>, used
          only for evaluation overlays. Capabilities outside this dataset are a source boundary,
          not a product failure.
        </p>
        <ul className="list-disc space-y-1 pl-5">
          <li>Network identity: no IP address or subnet</li>
          <li>Payment outcome: no success / failed / declined status</li>
          <li>Exact product/SKU identity: ProductCD is a category code only</li>
          <li>Calendar/festive context: no Diwali, sale calendar, or day of week</li>
          <li>Coordinated-abuse ground truth: no AttackSpec labels</li>
        </ul>
        <p>
          The IEEE-CIS classifier uses a chronological 70/10/20 <code>TransactionDT</code> split,
          train-only categorical encoding, and a validation-frozen operating threshold. Reported
          test metrics are historical IEEE-CIS results, not production accuracy.
        </p>
        <p>Amounts remain USD. No money-saved, ROI, or live payment-API performance is claimed.</p>
      </div>
    </details>
  )
}
