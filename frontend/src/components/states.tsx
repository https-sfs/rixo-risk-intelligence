export function LoadingState({ label }: { label: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-[10px] border border-line bg-panel px-4 py-6 text-sm text-mute"
    >
      {label}
    </div>
  )
}

export function ErrorState({ title, message }: { title: string; message: string }) {
  return (
    <div
      role="alert"
      className="rounded-[10px] border border-danger/20 bg-[#FEF2F2] px-4 py-5 text-sm"
    >
      <p className="font-semibold tracking-wide text-danger uppercase">{title}</p>
      <p className="mt-2 text-ink">{message}</p>
    </div>
  )
}

export function EmptyState({ title, message }: { title: string; message: string }) {
  return (
    <div className="rounded-[10px] border border-dashed border-line bg-panel px-4 py-8 text-sm">
      <p className="font-semibold text-ink">{title}</p>
      <p className="mt-2 text-mute">{message}</p>
    </div>
  )
}
