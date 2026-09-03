import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  analyzeCustomSession,
  confirmCustomMapping,
  getCustomSession,
  getCustomStatus,
  uploadCustomCsv,
} from '../api/client'
import { clearCustomSession, readCustomSession, rememberCustomSession } from '../api/customSession'
import { BRING_YOUR_DATA, SIMULATION_ONLY } from '../api/constants'
import { errorMessage, formatNumber } from '../api/format'
import {
  evaluationMetricsCopy,
  formatFraudLabelSummary,
  friendlyAnomalyTitle,
  friendlyCaseLabel,
} from '../api/presentation'
import { ErrorState, LoadingState } from '../components/states'

const CANONICAL = [
  'transaction_id',
  'amount',
  'timestamp',
  'fraud_label',
  'merchant',
  'account_id',
  'device_id',
  'ip_address',
  'product_sku',
  'payment_status',
] as const

const IDENTIFICATION = [
  { target: 'transaction_id', label: 'Transaction ID' },
  { target: 'amount', label: 'Amount' },
  { target: 'timestamp', label: 'Timestamp' },
  { target: 'product_sku', label: 'Product' },
  { target: 'fraud_label', label: 'Fraud label' },
] as const

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {}
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && !Number.isNaN(value) ? value : null
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} bytes`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes >= 1024 * 1024 * 1024) {
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB (${bytes.toLocaleString()} bytes)`
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB (${bytes.toLocaleString()} bytes)`
}

function mappingFromSession(payload: Record<string, unknown>): Record<string, string> {
  const nextMap: Record<string, string> = {}
  const mapped = asRecord(payload.mapping)
  for (const [key, value] of Object.entries(mapped)) {
    if (typeof value === 'string' && value) nextMap[key] = value
  }
  if (Object.keys(nextMap).length > 0) return nextMap
  const items = Array.isArray(payload.mapping_proposals)
    ? (payload.mapping_proposals as Record<string, unknown>[])
    : []
  for (const item of items) {
    if (item.auto_accepted && item.suggested) {
      nextMap[String(item.target)] = String(item.suggested)
    }
  }
  return nextMap
}

export function CustomUploadPage() {
  const { sessionId: routeSessionId } = useParams()
  const navigate = useNavigate()
  const [drag, setDrag] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [session, setSession] = useState<Record<string, unknown> | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [progress, setProgress] = useState<number | null>(null)
  const [maxBytes, setMaxBytes] = useState(1024 * 1024 * 1024)
  const [maxRows, setMaxRows] = useState(2_000_000)
  const [chunkBytes, setChunkBytes] = useState(3 * 1024 * 1024)
  const [reviewOpen, setReviewOpen] = useState(false)
  const [restoring, setRestoring] = useState(() => Boolean(routeSessionId || readCustomSession()))

  function applySession(payload: Record<string, unknown>) {
    setSession(payload)
    setMapping(mappingFromSession(payload))
    if (typeof payload.session_id === 'string') rememberCustomSession(payload.session_id)
  }

  useEffect(() => {
    const controller = new AbortController()
    getCustomStatus(controller.signal)
      .then((payload) => {
        const limits = asRecord(payload.upload_limits)
        if (typeof limits.max_bytes === 'number') setMaxBytes(limits.max_bytes)
        if (typeof limits.max_rows === 'number') setMaxRows(limits.max_rows)
        if (typeof limits.chunk_bytes === 'number' && limits.chunk_bytes > 0) {
          setChunkBytes(limits.chunk_bytes)
        }
      })
      .catch(() => {
        /* keep conservative local defaults */
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const remembered = readCustomSession()
    const target = routeSessionId || remembered
    if (!target) {
      setRestoring(false)
      return
    }
    if (!routeSessionId && remembered) {
      navigate(`/bring/${remembered}`, { replace: true })
      return
    }
    const controller = new AbortController()
    setError(null)
    setRestoring(true)
    getCustomSession(target, controller.signal)
      .then((payload) => {
        applySession(payload)
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        clearCustomSession()
        if (routeSessionId) {
          setError(errorMessage(err))
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setRestoring(false)
      })
    return () => controller.abort()
  }, [routeSessionId, navigate])

  const inspection = asRecord(session?.inspection)
  const compatibility = asRecord(session?.compatibility)
  const proposals = Array.isArray(session?.mapping_proposals)
    ? (session?.mapping_proposals as Record<string, unknown>[])
    : []
  const columns = Array.isArray(inspection.columns) ? (inspection.columns as string[]) : []
  const anomalies = Array.isArray(session?.anomalies)
    ? (session?.anomalies as Record<string, unknown>[])
    : []
  const summary = asRecord(session?.summary)
  const evaluation = asRecord(session?.evaluation)
  const sessionId = typeof session?.session_id === 'string' ? session.session_id : ''
  const status = typeof compatibility.status === 'string' ? compatibility.status : null
  const analyzed = summary.transactions_analyzed != null
  const setupOpen = !analyzed

  const mappingComplete = useMemo(() => {
    return Boolean(session?.mapping)
  }, [session])
  const mappingSummary = asRecord(session?.mapping_summary)
  const mappingValidation = asRecord(session?.mapping_validation)
  const identifiedCount = asNumber(mappingSummary.identified_count) ?? IDENTIFICATION.filter((field) => mapping[field.target]).length
  const analysisReady =
    Boolean(mapping.transaction_id) && Boolean(mapping.amount) && Boolean(mapping.timestamp)
  const missingRequired = IDENTIFICATION.filter(
    (field) =>
      (field.target === 'transaction_id' || field.target === 'amount' || field.target === 'timestamp') &&
      !mapping[field.target],
  )

  async function onFile(file: File | undefined) {
    if (!file) return
    setSelectedFile(file)
    setProgress(null)
    if (file.size > maxBytes) {
      setError(
        `Upload rejected: file is ${formatFileSize(file.size)}. The size limit is ${formatFileSize(maxBytes)}.`,
      )
      return
    }
    setBusy('upload')
    setError(null)
    try {
      const next = await uploadCustomCsv(
        file,
        (sent, total) => {
          setProgress(total > 0 ? Math.round((sent / total) * 100) : null)
        },
        { chunkBytes },
      )
      applySession(next)
      setProgress(100)
      setReviewOpen(false)
      if (typeof next.session_id === 'string') {
        navigate(`/bring/${next.session_id}`, { replace: true })
      }
    } catch (err: unknown) {
      setError(errorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  async function onConfirmMapping() {
    if (!sessionId) return
    setBusy('map')
    setError(null)
    try {
      const payload: Record<string, string | null> = {}
      for (const field of CANONICAL) {
        payload[field] = mapping[field] || null
      }
      applySession(await confirmCustomMapping(sessionId, payload))
    } catch (err: unknown) {
      setError(errorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  async function onAnalyze() {
    if (!sessionId) return
    setBusy('analyze')
    setError(null)
    try {
      applySession(await analyzeCustomSession(sessionId))
      navigate(`/bring/${sessionId}`, { replace: true })
    } catch (err: unknown) {
      setError(errorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-8">
      <header className="border border-brass/40 bg-brass/5 px-5 py-6">
        <p className="font-mono text-[11px] tracking-[0.2em] text-brass uppercase">
          {BRING_YOUR_DATA}
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">
          Your transactions. Our investigation engine.
        </h1>
        <p className="mt-3 max-w-2xl text-sm text-mute">
          Test the Fraud-Spike Investigator on your own transaction history. The upload stays in
          a local session. It is not mixed with Synthetic Demo, IEEE-CIS, or January 2026.
          Labels are never invented. {SIMULATION_ONLY} — Razorpay TEST MODE only, no live payment action.
        </p>
        <ol className="mt-5 grid gap-2 sm:grid-cols-4 xl:grid-cols-7 text-[10px] font-semibold tracking-[0.12em] uppercase">
          {['Upload', 'Map', 'Detect', 'Investigate', 'Decide', 'Simulate', 'Audit'].map((step) => (
            <li key={step} className="border border-line bg-panel px-2 py-2 text-center">
              {step}
            </li>
          ))}
        </ol>
      </header>

      {restoring && !session ? (
        <LoadingState label="Restoring the analyzed session…" />
      ) : null}

      {setupOpen && !restoring ? (
      <section
        className={[
          'border border-dashed px-5 py-8 text-center',
          drag ? 'border-brass bg-brass/10' : 'border-line bg-panel',
        ].join(' ')}
        onDragOver={(event) => {
          event.preventDefault()
          setDrag(true)
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDrag(false)
          void onFile(event.dataTransfer.files[0])
        }}
      >
          <h2 className="text-lg font-semibold">Upload CSV</h2>
        <p className="mt-2 text-sm text-mute">
          Minimum useful fields: transaction ID, amount, timestamp. Optional: merchant, account,
          device, IP, product/SKU, payment status, fraud label if genuinely available.
        </p>
        <label className="mt-5 inline-flex cursor-pointer bg-ink px-4 py-2.5 text-sm font-semibold text-canvas">
          {busy === 'upload' ? 'Reading CSV…' : 'Choose CSV file'}
          <input
            type="file"
            accept=".csv,text/csv"
            className="sr-only"
            onChange={(event) => void onFile(event.target.files?.[0])}
          />
        </label>
        <p className="mt-3 text-xs text-mute">Or drag and drop a CSV here. Isolated temporary file only.</p>
        <p className="mt-2 text-xs text-mute">
          Maximum file size: 1 GB · Maximum rows: 2,000,000
        </p>
        <p className="mt-1 text-xs text-mute">
          Current ceiling {formatFileSize(maxBytes)} · {maxRows.toLocaleString()} rows.
        </p>
        {selectedFile ? (
          <p className="mt-3 text-sm">
            Selected: {selectedFile.name} · {formatFileSize(selectedFile.size)}
          </p>
        ) : null}
        {busy === 'upload' && progress != null ? (
          <p className="mt-2 text-sm text-mute">Uploading {progress}%</p>
        ) : null}
      </section>
      ) : null}

      {error ? <ErrorState title="Bring Your Data could not continue" message={error} /> : null}

      {session && setupOpen ? (
        <section className="border border-line bg-panel p-5">
          <h2 className="text-lg font-semibold">Dataset</h2>
          <p className="mt-1 text-sm text-mute">
            {String(session.filename)} · local session {sessionId}
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <Fact
              label="Rows"
              value={
                asNumber(inspection.rows) != null
                  ? formatNumber(asNumber(inspection.rows))
                  : 'Counted during analysis'
              }
            />
            <Fact label="Columns" value={formatNumber(asNumber(inspection.column_count))} />
            <Fact
              label="File size"
              value={
                asNumber(session.file_bytes as number) != null
                  ? formatFileSize(Number(session.file_bytes))
                  : '—'
              }
            />
          </div>
        </section>
      ) : null}

      {session && setupOpen ? (
        <section className="border border-line bg-panel p-5">
          <h2 className="text-lg font-semibold">Fields identified</h2>
          <p className="mt-1 text-sm text-mute">
            {typeof mappingSummary.headline === 'string'
              ? mappingSummary.headline
              : `${identifiedCount}/5 required fields identified automatically.`}
          </p>
          <ul className="mt-4 space-y-2 text-sm">
            {IDENTIFICATION.map((field) => {
              const proposal = proposals.find((item) => item.target === field.target)
              const column = mapping[field.target] || (proposal?.auto_accepted ? String(proposal.suggested) : '')
              return (
                <li key={field.target} className="border border-line bg-raised px-4 py-3">
                  <span className="font-medium">{field.label}</span>
                  <span className="text-mute"> → </span>
                  {column ? (
                    <span>
                      {column} ✓
                    </span>
                  ) : (
                    <span className="text-mute">Not identified</span>
                  )}
                </li>
              )
            })}
          </ul>
          {missingRequired.length > 0 ? (
            <div className="mt-4 border border-line bg-raised px-4 py-3 text-sm">
              <p className="font-medium">Cannot continue until required fields are mapped.</p>
              {missingRequired.map((field) => {
                const proposal = proposals.find((item) => item.target === field.target)
                return (
                  <p key={field.target} className="mt-2 text-mute">
                    {typeof proposal?.question === 'string'
                      ? String(proposal.question)
                      : `Which column represents the ${field.label.toLowerCase()}?`}
                  </p>
                )
              })}
            </div>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => void onConfirmMapping()}
              disabled={busy != null || !analysisReady}
              className="bg-ink px-4 py-2.5 text-sm font-semibold text-canvas disabled:opacity-50"
            >
              {busy === 'map' ? 'Saving mapping…' : 'Confirm and continue'}
            </button>
            <button
              type="button"
              onClick={() => setReviewOpen((open) => !open)}
              className="border border-line bg-panel px-4 py-2.5 text-sm font-semibold"
            >
              {reviewOpen ? 'Hide mapping table' : 'Review mappings'}
            </button>
          </div>
        </section>
      ) : null}

      {session && setupOpen && reviewOpen ? (
        <section className="border border-line bg-panel p-5">
          <h2 className="text-lg font-semibold">Review mappings</h2>
          <p className="mt-1 text-sm text-mute">
            Advanced adjustment only. Low-confidence guesses are never accepted automatically.
          </p>
          {proposals
            .filter((item) => item.ambiguous || item.confidence === 'low')
            .map((item) => (
              <div key={String(item.target)} className="mt-4 border border-line bg-raised px-4 py-3">
                <p className="text-sm font-medium">{String(item.question ?? item.label)}</p>
                <p className="mt-1 text-xs text-mute">{String(item.reason ?? '')}</p>
                {(Array.isArray(item.candidates) ? (item.candidates as string[]) : []).length > 0 ? (
                  <p className="mt-2 text-xs text-mute">
                    Candidates: {(item.candidates as string[]).join(', ')}
                  </p>
                ) : null}
              </div>
            ))}
          <div className="table-wrap mt-4 border border-line">
            <table className="w-full text-left text-sm">
              <thead className="bg-raised text-[11px] tracking-[0.12em] text-mute uppercase">
                <tr>
                  <th className="px-3 py-2 font-medium">Field</th>
                  <th className="px-3 py-2 font-medium">Your column</th>
                  <th className="px-3 py-2 font-medium">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {CANONICAL.map((field) => {
                  const proposal = proposals.find((item) => item.target === field)
                  const label =
                    IDENTIFICATION.find((item) => item.target === field)?.label ??
                    field.replaceAll('_', ' ')
                  return (
                    <tr key={field} className="border-t border-line">
                      <td className="px-3 py-2">{label}</td>
                      <td className="px-3 py-2">
                        <select
                          className="w-full border border-line bg-canvas px-2 py-1"
                          value={mapping[field] ?? ''}
                          onChange={(event) =>
                            setMapping((current) => ({
                              ...current,
                              [field]: event.target.value,
                            }))
                          }
                        >
                          <option value="">— not mapped —</option>
                          {columns.map((column) => (
                            <option key={column} value={column}>
                              {column}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="px-3 py-2 text-mute">
                        {proposal?.ambiguous
                          ? 'Ambiguous — choose'
                          : typeof proposal?.confidence === 'string'
                            ? String(proposal.confidence)
                            : 'unmapped'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <button
            type="button"
            onClick={() => void onConfirmMapping()}
            disabled={busy != null}
            className="mt-4 bg-ink px-4 py-2.5 text-sm font-semibold text-canvas disabled:opacity-50"
          >
            {busy === 'map' ? 'Saving mapping…' : 'Save reviewed mapping'}
          </button>
        </section>
      ) : null}

      {session && setupOpen ? (
        <section className="border border-line bg-panel p-5">
          <h2 className="text-lg font-semibold">Progress</h2>
          <ol className="mt-4 space-y-2 text-sm">
            {[
              { id: 'upload', label: 'Upload complete', done: true },
              { id: 'inspect', label: 'Dataset inspected', done: true },
              { id: 'map', label: 'Fields mapped', done: mappingComplete },
              {
                id: 'detect',
                label: 'Detecting anomalies',
                done: summary.transactions_analyzed != null,
                active: busy === 'analyze',
              },
              {
                id: 'analyze',
                label: 'Running analysis',
                done: summary.transactions_analyzed != null,
                active: busy === 'analyze' && mappingComplete,
              },
              {
                id: 'investigate',
                label: 'Preparing investigation',
                done: anomalies.length > 0 || (summary.transactions_analyzed != null && anomalies.length === 0),
              },
            ].map((step) => (
              <li key={step.id} className={step.active ? 'font-medium' : 'text-mute'}>
                {step.done ? '✓' : step.active ? '●' : '○'} {step.label}
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {setupOpen && mappingComplete && compatibility.status ? (
        <section className="border border-brass/40 bg-panel p-5">
          <p className="font-mono text-[11px] tracking-[0.2em] text-brass uppercase">
            Model compatibility
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight">
            {String(compatibility.headline)}
          </h2>
          <p className="mt-3 text-sm">{String(compatibility.reason)}</p>
          {mappingValidation.ready === false ? (
            <p className="mt-3 text-sm">{String(mappingValidation.reason)}</p>
          ) : null}
          {status === 'compatible' ? (
            <p className="mt-3 text-sm text-mute">
              Supervised fraud-risk analysis available: PR-AUC · ROC-AUC · Recall · Precision · F1
              + independent anomaly detection. Provenance is MODEL PREDICTION · USER DATASET, not
              live production detection.
            </p>
          ) : (
            <p className="mt-3 text-sm text-mute">
              Continue with anomaly investigation from the fields that are actually present.
            </p>
          )}
          <button
            type="button"
            onClick={() => void onAnalyze()}
            disabled={busy != null || mappingValidation.ready === false}
            className="mt-4 bg-brass px-4 py-2.5 text-sm font-semibold text-canvas disabled:opacity-50"
          >
            {busy === 'analyze' ? 'Analyzing…' : 'Continue with anomaly investigation'}
          </button>
        </section>
      ) : null}

      {analyzed ? (
        <section className="border border-line bg-panel p-5">
          <h2 className="text-lg font-semibold">Detection summary</h2>
          <p className="mt-1 text-sm text-mute">
            {String(session?.filename ?? 'Uploaded CSV')} is still in this investigation session.
            You do not need to upload it again.
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Fact
              label="Transactions analyzed"
              value={formatNumber(asNumber(summary.transactions_analyzed))}
            />
            <Fact
              label="Temporal anomalies"
              value={formatNumber(asNumber(summary.temporal_anomalies))}
            />
            <Fact
              label="Amount-concentration anomalies"
              value={formatNumber(asNumber(summary.amount_concentration_anomalies))}
            />
            <Fact
              label="Entity-concentration anomalies"
              value={formatNumber(asNumber(summary.entity_concentration_anomalies))}
            />
          </div>
          {evaluation.available ? (
            <div className="mt-5 border-t border-line pt-4">
              <p className="text-[11px] tracking-[0.12em] text-mute uppercase">
                {
                  formatFraudLabelSummary(
                    asNumber(evaluation.fraud_count),
                    asNumber(evaluation.fraud_rate),
                    asNumber(summary.transactions_analyzed),
                  ).title
                }
              </p>
              <p className="mt-2 text-sm">
                {
                  formatFraudLabelSummary(
                    asNumber(evaluation.fraud_count),
                    asNumber(evaluation.fraud_rate),
                    asNumber(summary.transactions_analyzed),
                  ).detail
                }
                {evaluation.classifier_metrics_calculated
                  ? ` · PR-AUC ${formatNumber(asNumber(asRecord(evaluation.ranking).pr_auc))} · ROC-AUC ${formatNumber(asNumber(asRecord(evaluation.ranking).roc_auc))} · F1 ${formatNumber(asNumber(evaluation.f1))}`
                  : ''}
              </p>
              {(() => {
                const copy = evaluationMetricsCopy(
                  typeof evaluation.reason === 'string' ? evaluation.reason : null,
                  Boolean(evaluation.classifier_metrics_calculated),
                )
                return (
                  <>
                    <p className="mt-2 text-sm font-medium">{copy.headline}</p>
                    {copy.detail ? <p className="mt-1 text-xs text-mute">{copy.detail}</p> : null}
                    {copy.technical ? (
                      <details className="mt-2">
                        <summary className="cursor-pointer text-xs text-mute">
                          Why are classifier metrics unavailable?
                        </summary>
                        <p className="mt-1 font-mono text-xs text-mute">{copy.technical}</p>
                      </details>
                    ) : null}
                  </>
                )
              })()}
            </div>
          ) : null}
        </section>
      ) : null}

      {anomalies.length > 0 ? (
        <section>
          <h2 className="text-lg font-semibold">Anomalies</h2>
          <p className="mt-1 text-sm text-mute">
            Open a case to walk Decision → Approval → Simulation → Audit. Returning here keeps
            this analyzed session — you do not need to upload the CSV again.
          </p>
          <ul className="mt-4 space-y-2">
            {anomalies.map((item) => (
              <li key={String(item.anomaly_id)} className="border border-line bg-panel">
                <Link
                  to={`/bring/${sessionId}/anomalies/${String(item.anomaly_id)}`}
                  className="block px-4 py-3 hover:bg-raised"
                >
                  <p className="font-medium">{friendlyAnomalyTitle(String(item.kind))}</p>
                  <p className="mt-1 text-xs text-mute">{friendlyCaseLabel(String(item.anomaly_id))}</p>
                  <p className="mt-1 text-sm text-mute">
                    {typeof item.time_display === 'string' ? item.time_display : ''}
                    {item.time_display ? ' · ' : ''}
                    {formatNumber(asNumber(item.transactions))} transactions
                    {item.amount != null && !Number.isNaN(asNumber(item.amount))
                      ? ` · amount ${formatNumber(asNumber(item.amount))}`
                      : ''}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {analyzed ? (
        <section
          className={[
            'border border-dashed px-5 py-8 text-center',
            drag ? 'border-brass bg-brass/10' : 'border-line bg-panel',
          ].join(' ')}
          onDragOver={(event) => {
            event.preventDefault()
            setDrag(true)
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(event) => {
            event.preventDefault()
            setDrag(false)
            void onFile(event.dataTransfer.files[0])
          }}
        >
          <h2 className="text-lg font-semibold">Upload a different CSV</h2>
          <p className="mt-2 text-sm text-mute">
            Starts a new isolated session. The current analyzed dataset stays available until you
            replace it.
          </p>
          <label className="mt-5 inline-flex cursor-pointer bg-ink px-4 py-2.5 text-sm font-semibold text-canvas">
            {busy === 'upload' ? 'Reading CSV…' : 'Choose CSV file'}
            <input
              type="file"
              accept=".csv,text/csv"
              className="sr-only"
              onChange={(event) => void onFile(event.target.files?.[0])}
            />
          </label>
        </section>
      ) : null}
    </div>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-line bg-raised px-4 py-3">
      <p className="text-[11px] tracking-[0.12em] text-mute uppercase">{label}</p>
      <p className="mt-1 text-xl font-semibold">{value}</p>
    </div>
  )
}
