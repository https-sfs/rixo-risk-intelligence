import type { RecommendedAction } from './types'

export function formatPercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return 'Unavailable'
  return `${(value * 100).toFixed(2)}%`
}

export function formatConfidence(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return 'Unavailable'
  const ratio = value > 1 ? value / 100 : value
  return `${Math.round(ratio * 100)}%`
}

export function formatRatio(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return 'Baseline unavailable'
  return `${value.toFixed(2)}×`
}

export function formatNumber(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('en-IN').format(value)
}

export function formatUsd(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(value)
}

export function formatUsdCompact(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  const abs = Math.abs(value)
  if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return `$${(value / 1_000).toFixed(1)}K`
  return formatUsd(value)
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return '—'
  if (value.startsWith('relative-hour-')) {
    const bucket = Number(value.split('-').at(-1))
    return Number.isFinite(bucket) ? `Relative hour ${bucket.toLocaleString('en-US')}` : 'Relative hour'
  }
  if (value.startsWith('1970-01-01')) {
    return 'Relative dataset hour'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  const day = date.getDate()
  const month = months[date.getMonth()]
  const year = date.getFullYear()
  let hours = date.getHours()
  const minutes = String(date.getMinutes()).padStart(2, '0')
  const suffix = hours >= 12 ? 'PM' : 'AM'
  hours = hours % 12
  if (hours === 0) hours = 12
  return `${day} ${month} ${year} · ${hours}:${minutes} ${suffix}`
}

export function formatTechnicalTimestamp(value: string | null | undefined): string {
  return value && String(value).trim() ? String(value) : '—'
}

export function formatTemporalWindow(
  display: string | null | undefined,
  hourStart: string | null | undefined,
  timeKind?: string | null,
): string {
  const looksIso = (value: string) => /^\d{4}-\d{2}-\d{2}T/.test(value) || value.includes('1970')
  if (display && !looksIso(display)) return display
  if (timeKind === 'relative_elapsed') return formatTimestamp(hourStart)
  return formatTimestamp(hourStart ?? display)
}

export function providerLabel(provider: string | null | undefined): string {
  const raw = (provider ?? '').toLowerCase()
  if (raw.includes('llm') && !raw.includes('deterministic')) return 'Assisted review'
  if (raw.includes('deterministic')) return 'Rule-based analysis'
  return provider || 'Rule-based analysis'
}

export function verdictLabel(verdict: string): string {
  return verdict.replaceAll('_', ' ')
}

export function actionLabel(type: string): string {
  return type.replaceAll('_', ' ')
}

export function isPassiveAction(action: RecommendedAction): boolean {
  return action.type === 'monitor' || action.type === 'no_action'
}

export function skuSummary(value: unknown): string {
  if (!Array.isArray(value) || value.length === 0) return '—'
  return value
    .slice(0, 3)
    .map((item) => {
      if (item && typeof item === 'object' && 'sku_id' in item) {
        return String((item as { sku_id: string }).sku_id)
      }
      return String(item)
    })
    .join(', ')
}

export function reasonList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String)
  if (typeof value === 'string') {
    try {
      const parsed: unknown = JSON.parse(value)
      return Array.isArray(parsed) ? parsed.map(String) : [value]
    } catch {
      return [value]
    }
  }
  return []
}

export function isCoordinatedType(spikeType: string): boolean {
  return spikeType.toLowerCase().includes('coord')
}

export function isFestiveType(spikeType: string): boolean {
  return spikeType.toLowerCase().includes('fest')
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return 'Request failed'
}
