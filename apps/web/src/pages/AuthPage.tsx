import { Navigate } from 'react-router-dom'
import { AuthLayout } from '../components/auth/AuthLayout'
import { AuthTabs } from '../components/auth/AuthTabs'
import { useAuth } from '../context/AuthContext'

export function AuthPage() {
  const { isAuthenticated, isLoading } = useAuth()

  if (!isLoading && isAuthenticated) {
    return <Navigate to="/" replace />
  }

  return (
    <AuthLayout>
      <AuthTabs />
    </AuthLayout>
  )
}
