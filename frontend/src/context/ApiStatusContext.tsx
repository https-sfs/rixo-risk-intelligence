import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { checkApiHealth } from '../api/client'
import { errorMessage } from '../api/format'

export type ApiConnection = 'checking' | 'connected' | 'offline'

type ApiStatusValue = {
  connection: ApiConnection
  message: string | null
  refresh: () => void
}

const ApiStatusContext = createContext<ApiStatusValue | null>(null)

export function ApiStatusProvider({ children }: { children: ReactNode }) {
  const [connection, setConnection] = useState<ApiConnection>('checking')
  const [message, setMessage] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setConnection('checking')
    checkApiHealth(controller.signal)
      .then((data) => {
        if (data.status === 'ok') {
          setConnection('connected')
          setMessage(null)
        } else {
          setConnection('offline')
          setMessage(`Unexpected health status: ${data.status}`)
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setConnection('offline')
        setMessage(errorMessage(error))
      })
    return () => controller.abort()
  }, [tick])

  return (
    <ApiStatusContext.Provider
      value={{
        connection,
        message,
        refresh: () => setTick((value) => value + 1),
      }}
    >
      {children}
    </ApiStatusContext.Provider>
  )
}

export function useApiStatus(): ApiStatusValue {
  const value = useContext(ApiStatusContext)
  if (!value) {
    throw new Error('useApiStatus must be used within ApiStatusProvider')
  }
  return value
}
