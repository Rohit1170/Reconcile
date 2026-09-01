'use client'

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { api, ApiError, TOKEN_STORAGE_KEY, type User } from './api'

type AuthContextValue = {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  signup: (name: string, email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const router = useRouter()

  useEffect(() => {
    const stored = sessionStorage.getItem(TOKEN_STORAGE_KEY)
    if (!stored) {
      setLoading(false)
      return
    }
    api
      .me()
      .then(setUser)
      .catch(() => sessionStorage.removeItem(TOKEN_STORAGE_KEY))
      .finally(() => setLoading(false))
  }, [])

  async function login(email: string, password: string) {
    const res = await api.login(email, password)
    sessionStorage.setItem(TOKEN_STORAGE_KEY, res.access_token)
    setUser(await api.me())
  }

  async function signup(name: string, email: string, password: string) {
    const res = await api.signup(name, email, password)
    sessionStorage.setItem(TOKEN_STORAGE_KEY, res.access_token)
    setUser(await api.me())
  }

  function logout() {
    sessionStorage.removeItem(TOKEN_STORAGE_KEY)
    setUser(null)
    router.replace('/login')
  }

  return <AuthContext.Provider value={{ user, loading, login, signup, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

export function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401
}
