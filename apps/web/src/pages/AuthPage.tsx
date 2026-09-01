import { Navigate } from 'react-router-dom'
import { AuthLayout } from '../components/auth/AuthLayout'
import { AuthTabs } from '../components/auth/AuthTabs'
import { useAuth } from '../context/AuthContext'

export function AuthPage() {
  const { isAuthenticated, isLoading } = useAuth()

  // Straight to the console, not to `/`. The landing page is public marketing
  // and every button on it points back here, so sending a signed-in user there
  // leaves them bouncing between the two with no way into the dashboard.
  if (!isLoading && isAuthenticated) {
    return <Navigate to="/queue" replace />
  }

  return (
    <AuthLayout>
      <AuthTabs />
    </AuthLayout>
  )
}
