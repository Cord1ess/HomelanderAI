import { Navigate, Route, Routes } from 'react-router-dom'

import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { AuthPage } from './pages/AuthPage'
import { RegisterCarrierPage } from './pages/RegisterCarrierPage'
import { StaffManagementPage } from './pages/admin/StaffManagementPage'
import { EscalationsPage } from './pages/escalations/EscalationsPage'
import { HomePage } from './pages/home/HomePage'
import { IntakePage } from './pages/intake/IntakePage'
import { AppLayout } from './pages/layout/AppLayout'
import { NotificationsPage } from './pages/notifications/NotificationsPage'
import { PortalPage } from './pages/portal/PortalPage'
import { PricingPage } from './pages/pricing/PricingPage'
import { ProfilePage } from './pages/profile/ProfilePage'
import { QueuePage } from './pages/queue/QueuePage'
import { ReviewPage } from './pages/review/ReviewPage'

/**
 * Routes.
 *
 * Public:
 *   /                      Home landing (hero + sign-in CTA)
 *   /auth                  Sign in: staff, or a client (/auth?as=client)
 *   /auth/register-carrier Onboard a carrier. Deliberately linked from nowhere.
 *   /portal                Client portal. Its own sign-in and cookie, so it is
 *                          not behind ProtectedRoute; it sends itself back to
 *                          the client sign-in when there is no portal session.
 *
 * Guarded by ProtectedRoute -> AppLayout (the console):
 *   /queue                 Queue - role-tailored view
 *   /escalations           Escalation inbox. Medical Professional and Administrator only
 *   /admin/users           Staff accounts and carrier settings. Administrator only
 *   /applications/new      Intake form
 *   /applications/:id      Review workspace
 *   /notifications         Notification list
 *   /pricing               Plan and premium per risk tier
 *   /profile               Operator profile & workspace authority
 */
export function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/auth" element={<AuthPage />} />
      <Route path="/auth/register-carrier" element={<RegisterCarrierPage />} />
      <Route path="/portal" element={<PortalPage />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/queue" element={<QueuePage />} />
        {/* The two screens that belong to one role. The API enforces the same
            rules; these guards stop the screen being opened by typing its
            address, which the role-specific navigation alone never did. */}
        <Route
          path="/escalations"
          element={
            <ProtectedRoute allowedRoles={['medical_professional', 'admin']}>
              <EscalationsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/users"
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <StaffManagementPage />
            </ProtectedRoute>
          }
        />
        <Route path="/applications/new" element={<IntakePage />} />
        <Route path="/applications/:id" element={<ReviewPage />} />
        <Route path="/notifications" element={<NotificationsPage />} />
        <Route path="/pricing" element={<PricingPage />} />
        <Route path="/profile" element={<ProfilePage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
