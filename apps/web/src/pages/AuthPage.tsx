import { Navigate, useSearchParams } from 'react-router-dom'
import { AuthLayout } from '../components/auth/AuthLayout'
import { AuthTabs } from '../components/auth/AuthTabs'
import { useAuth } from '../context/AuthContext'

export function AuthPage() {
  const { isAuthenticated, isLoading } = useAuth()
  const [params] = useSearchParams()
  const wantsClientSignIn = params.get('as') === 'client'

  // Straight to the console, not to `/`. The landing page is public marketing
  // and every button on it points back here, so sending a signed-in user there
  // leaves them bouncing between the two with no way into the dashboard.
  //
  // Except when the client sign-in was asked for. A staff session says nothing
  // about the portal, which has its own cookie, and an operator showing a
  // client their portal from the same browser must not be bounced into the
  // console instead.
  if (!isLoading && isAuthenticated && !wantsClientSignIn) {
    return <Navigate to="/queue" replace />
  }

  return (
    <AuthLayout>
      <AuthTabs />
    </AuthLayout>
  )
}
