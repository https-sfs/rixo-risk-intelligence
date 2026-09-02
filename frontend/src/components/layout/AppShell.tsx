import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  HUMAN_APPROVAL_REQUIRED,
  REAL_PUBLIC_DATA,
  RECENT_PUBLIC_DATA,
  BRING_YOUR_DATA,
  SIMULATION_ONLY,
  SYNTHETIC_PROVENANCE,
} from '../../api/constants'
import { useApiStatus } from '../../context/ApiStatusContext'
import { BrandMark, WorkflowStrip } from '../ui'

const NAV = [
  { to: '/', label: 'Overview', end: true },
  { to: '/investigations', label: 'Investigations', end: false },
  { to: '/actions', label: 'Actions', end: true },
  { to: '/audit', label: 'Audit', end: true },
]

const WORLDS = [
  { to: '/', label: 'Synthetic Demo', end: true, match: 'synthetic' },
  { to: '/real', label: 'IEEE-CIS', end: false, match: 'real' },
  { to: '/recent', label: 'Jan 2026', end: false, match: 'recent' },
  { to: '/bring', label: 'Bring Your Data', end: false, match: 'custom' },
]

function navClass(active: boolean): string {
  return [
    'block border-l-2 px-3 py-2.5 text-sm font-medium',
    active
      ? 'border-brass bg-raised text-brass'
      : 'border-transparent text-navy hover:bg-canvas hover:text-brass',
  ].join(' ')
}

function worldClass(active: boolean): string {
  return [
    'block rounded-md px-3 py-2 text-sm',
    active ? 'bg-raised font-medium text-brass' : 'text-mute hover:bg-canvas hover:text-navy',
  ].join(' ')
}

export function AppShell() {
  const { connection, message, refresh } = useApiStatus()
  const [open, setOpen] = useState(false)
  const location = useLocation()
  const realWorld = location.pathname.startsWith('/real')
  const recentWorld = location.pathname.startsWith('/recent')
  const customWorld = location.pathname.startsWith('/bring')
  const customSessionMatch = location.pathname.match(/^\/bring\/([^/]+)/)
  const bringHome = customSessionMatch ? `/bring/${customSessionMatch[1]}` : '/bring'
  const nav = customWorld
    ? [{ to: bringHome, label: 'Bring your data', end: true }]
    : recentWorld
      ? [{ to: '/recent', label: 'Jan 2026', end: true }]
      : realWorld
        ? [{ to: '/real', label: 'IEEE-CIS', end: true }]
        : NAV

  const apiLabel =
    connection === 'connected'
      ? 'Connected'
      : connection === 'checking'
        ? 'Checking'
        : 'API offline'

  const worldLabel = customWorld
    ? BRING_YOUR_DATA
    : recentWorld
      ? RECENT_PUBLIC_DATA
      : realWorld
        ? REAL_PUBLIC_DATA
        : SYNTHETIC_PROVENANCE

  const environmentLabel = customWorld
    ? 'Environment: Bring your data'
    : recentWorld
      ? 'Environment: Jan 2026'
      : realWorld
        ? 'Environment: IEEE-CIS'
        : 'Environment: Demo / Simulation'

  const loop = customWorld
    ? 'UPLOAD → MAP → DETECT → INVESTIGATE → DECIDE → SIMULATE → AUDIT'
    : recentWorld || realWorld
      ? 'DETECT → INVESTIGATE → REASON → DECIDE → HUMAN APPROVAL → SIMULATED ACTION → AUDIT'
      : 'DETECT → INVESTIGATE → DECIDE → ACT → VERIFY'

  return (
    <div className="min-h-svh bg-canvas text-ink">
      <div className="border-b border-warning/20 bg-[#FFF7ED] px-4 py-2 text-center text-xs font-semibold tracking-[0.16em] text-warning uppercase">
        {customWorld
          ? 'BRING YOUR DATA — user-provided CSV — local session only — SIMULATED ACTIONS ONLY'
          : recentWorld
            ? 'RECENT PUBLIC DATA — January 2026 — SIMULATED ACTIONS ONLY'
            : realWorld
              ? 'REAL PUBLIC DATA — IEEE-CIS — SIMULATED ACTIONS ONLY'
              : 'Demo / simulation environment — SIMULATED ACTIONS ONLY'}
      </div>
      <div className="flex min-h-[calc(100svh-36px)]">
        {open ? (
          <button
            type="button"
            aria-label="Close navigation"
            className="fixed inset-0 z-20 bg-navy/40 md:hidden"
            onClick={() => setOpen(false)}
          />
        ) : null}

        <aside
          id="app-nav"
          className={[
            'z-30 flex w-64 shrink-0 flex-col border-r border-line bg-panel',
            'fixed inset-y-0 left-0 md:static',
            open ? 'translate-x-0' : '-translate-x-full md:translate-x-0',
          ].join(' ')}
        >
          <div className="border-b border-line px-4 py-5">
            <BrandMark />
            <p className="mt-3 text-[10px] font-medium tracking-[0.12em] text-mute uppercase">
              {worldLabel}
            </p>
          </div>
          <nav aria-label="Primary" className="flex-1 overflow-y-auto px-2 py-4">
            {nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) => navClass(isActive)}
                onClick={() => setOpen(false)}
              >
                {item.label}
              </NavLink>
            ))}
            <p className="mt-6 mb-2 px-3 text-[11px] font-semibold tracking-[0.14em] text-mute uppercase">
              Data
            </p>
            <div className="grid grid-cols-1 gap-1">
              {WORLDS.map((item) => (
                <NavLink
                  key={item.label}
                  to={item.to}
                  end={item.end}
                  className={() => {
                    const active =
                      item.match === 'synthetic'
                        ? !realWorld && !recentWorld && !customWorld
                        : item.match === 'real'
                          ? realWorld
                          : item.match === 'recent'
                            ? recentWorld
                            : customWorld
                    return worldClass(active)
                  }}
                  onClick={() => setOpen(false)}
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
          </nav>
          <div className="border-t border-line px-4 py-4">
            <p className="text-[11px] tracking-[0.16em] text-mute uppercase">System</p>
            <p className="mt-2 text-sm">
              API status:{' '}
              <span
                className={
                  connection === 'connected'
                    ? 'text-success'
                    : connection === 'offline'
                      ? 'text-danger'
                      : 'text-warning'
                }
              >
                {apiLabel}
              </span>
            </p>
            {message && connection === 'offline' ? (
              <p className="mt-1 text-xs text-mute">{message}</p>
            ) : null}
            <button
              type="button"
              onClick={refresh}
              className="mt-3 text-xs font-medium text-brass underline-offset-2 hover:underline"
            >
              Recheck API
            </button>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex items-center justify-between gap-3 border-b border-line bg-panel px-4 py-3">
            <button
              type="button"
              className="min-h-11 border border-line px-3 py-2 text-sm md:hidden"
              aria-expanded={open}
              aria-controls="app-nav"
              onClick={() => setOpen((value) => !value)}
            >
              Menu
            </button>
            <div className="min-w-0">
              <WorkflowStrip steps={loop} />
              <p className="mt-1 truncate text-[11px] text-mute">
                {customWorld
                  ? `Your upload stays in a local session. It is not mixed with the three benchmark worlds. Actions are ${SIMULATION_ONLY}.`
                  : recentWorld
                    ? `January 2026 historical analysis. is_fraud is delayed ground truth only. Actions are ${SIMULATION_ONLY}. Razorpay TEST MODE only; no real money is moved.`
                    : realWorld
                      ? `IEEE-CIS historical analysis. isFraud is delayed ground truth only. Actions are ${SIMULATION_ONLY}. Razorpay TEST MODE only; no real money is moved.`
                      : `ACT: Recommend → ${HUMAN_APPROVAL_REQUIRED} → Simulate (${SIMULATION_ONLY}). VERIFY: simulation / audit state only — not production fraud reduction.`}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2 text-[11px] font-semibold tracking-[0.08em] uppercase">
              <span className="rounded-md border border-line bg-raised px-2.5 py-1.5 text-navy">
                {environmentLabel}
              </span>
              <span
                className={
                  connection === 'connected'
                    ? 'rounded-md border border-success/20 bg-[#ECFDF3] px-2.5 py-1.5 text-success'
                    : connection === 'offline'
                      ? 'rounded-md border border-danger/20 bg-[#FEF2F2] px-2.5 py-1.5 text-danger'
                      : 'rounded-md border border-warning/20 bg-[#FFF7ED] px-2.5 py-1.5 text-warning'
                }
              >
                API: {apiLabel}
              </span>
            </div>
          </header>
          <main className="flex-1 px-4 py-6 md:px-8">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  )
}
