import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { Navigate, useLocation } from 'react-router-dom'

/**
 * Minimal in-memory auth for the frontend until the backend auth endpoints
 * exist (Phase 0 API exposes only /api/health).
 *
 * The session lives in React state ONLY — never localStorage/sessionStorage —
 * so a refresh returns to the login page, and no token ever reaches
 * JavaScript, matching DASHBOARD.md's httpOnly-cookie rule in spirit.
 *
 * TODO: replace this mock with the real flow when /api/auth/* lands:
 *   1. POST /api/auth/login  → server sets httpOnly cookie
 *   2. GET  /api/auth/me     → user + tenant + role (bootstraps the session)
 *   3. POST /api/auth/logout → clears the cookie
 *   4. Any 401 from an API call → clear session + navigate to /login?expired=1
 * See docs/DashboardImplementation.md.
 */

export interface SessionUser {
  email: string
  role: 'operator' | 'underwriter'
  tenant: string
}

interface AuthContextValue {
  user: SessionUser | null
  signIn: (email: string) => void
  signOut: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null)

  const signIn = useCallback((email: string) => {
    setUser({
      email,
      role: 'underwriter',
      tenant: 'demo-carrier',
    })
    // TODO: GET /api/auth/me once the httpOnly cookie is set by the server.
  }, [])

  const signOut = useCallback(() => {
    setUser(null)
    // TODO: POST /api/auth/logout.
  }, [])

  const value = useMemo(() => ({ user, signIn, signOut }), [user, signIn, signOut])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const location = useLocation()

  if (!user) {
    return <Navigate to="/login?expired=1" replace state={{ from: location }} />
  }
  return <>{children}</>
}
