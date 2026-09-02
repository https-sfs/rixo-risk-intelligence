type Tone = 'danger' | 'warning' | 'success' | 'neutral' | 'info'

const TONE_CLASS: Record<Tone, string> = {
  danger: 'border-danger/20 bg-[#FEF2F2] text-danger',
  warning: 'border-warning/20 bg-[#FFF7ED] text-warning',
  success: 'border-success/20 bg-[#ECFDF3] text-success',
  info: 'border-brass/20 bg-raised text-brass',
  neutral: 'border-line bg-canvas text-mute',
}

export function StatusBadge({
  label,
  tone = 'neutral',
}: {
  label: string
  tone?: Tone
}) {
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-semibold tracking-[0.12em] uppercase ${TONE_CLASS[tone]}`}
    >
      {label}
    </span>
  )
}

export function severityTone(severity: string): Tone {
  const value = severity.toLowerCase()
  if (value === 'high' || value === 'critical') return 'danger'
  if (value === 'medium') return 'warning'
  if (value === 'info' || value === 'low') return 'success'
  return 'neutral'
}

export function verdictTone(verdict: string): Tone {
  if (verdict === 'coordinated_abuse') return 'danger'
  if (verdict === 'likely_festive') return 'success'
  if (verdict === 'inconclusive') return 'warning'
  return 'neutral'
}
