import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'

import { useAuth } from '../../context/AuthContext'

/**
 * The pages that are the underwriters' and the administrators': the queue,
 * taking an application, analytics, pricing. A doctor who follows a link to one
 * is taken to their own reviews rather than shown a refusal; the API refuses
 * them the same things regardless.
 */
export function NotForDoctors({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  if (user?.role === 'medical_professional') return <Navigate to="/escalations" replace />
  return <>{children}</>
}
