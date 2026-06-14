import { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'

interface UserContextValue {
  userId: string | null
  loading: boolean
}

const UserContext = createContext<UserContextValue>({ userId: null, loading: true })

export function UserProvider({ children }: { children: ReactNode }) {
  const [userId, setUserId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/users/me', { credentials: 'include' })
      .then(r => r.json())
      .then(data => setUserId(data.user_id))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  return (
    <UserContext.Provider value={{ userId, loading }}>
      {children}
    </UserContext.Provider>
  )
}

export const useCurrentUser = () => useContext(UserContext)
