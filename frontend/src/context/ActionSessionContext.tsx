import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'

const STORAGE_KEY = 'fsi.actionIds'

function readStoredIds(): string[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === 'string') : []
  } catch {
    return []
  }
}

type ActionSessionValue = {
  actionIds: string[]
  rememberAction: (actionId: string) => void
}

const ActionSessionContext = createContext<ActionSessionValue | null>(null)

export function ActionSessionProvider({ children }: { children: ReactNode }) {
  const [actionIds, setActionIds] = useState<string[]>(readStoredIds)

  const value = useMemo<ActionSessionValue>(
    () => ({
      actionIds,
      rememberAction: (actionId: string) => {
        setActionIds((current) => {
          if (current.includes(actionId)) return current
          const next = [...current, actionId]
          sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next))
          return next
        })
      },
    }),
    [actionIds],
  )

  return (
    <ActionSessionContext.Provider value={value}>{children}</ActionSessionContext.Provider>
  )
}

export function useActionSession(): ActionSessionValue {
  const value = useContext(ActionSessionContext)
  if (!value) {
    throw new Error('useActionSession must be used within ActionSessionProvider')
  }
  return value
}
