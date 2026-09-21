import { Navigate, useNavigate } from 'react-router-dom'
import { AuthLayout } from '../components/auth/AuthLayout'
import { RegisterTenantForm } from '../components/auth/RegisterTenantForm'
import { useAuth } from '../context/AuthContext'

/**
 * Onboard a new carrier. Reachable only by typing the address: carriers are
 * brought on by us, not by whoever finds the sign-in page, so nothing public
 * links here.
 */
export function RegisterCarrierPage() {
  const navigate = useNavigate()
  const { isAuthenticated, isLoading } = useAuth()

  if (!isLoading && isAuthenticated) {
    return <Navigate to="/queue" replace />
  }

  return (
    <AuthLayout>
      <RegisterTenantForm onSwitchToLogin={() => navigate('/auth')} />
    </AuthLayout>
  )
}
