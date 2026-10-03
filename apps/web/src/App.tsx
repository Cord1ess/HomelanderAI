import { Navigate, Route, Routes } from 'react-router-dom'

import { NotForDoctors } from './components/auth/NotForDoctors'
import { OwnerOnly } from './components/auth/OwnerOnly'
import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { AuthPage } from './pages/AuthPage'
import { RegisterCarrierPage } from './pages/RegisterCarrierPage'
import { AccessRequestsPage } from './pages/admin/AccessRequestsPage'
import { DataRequestsPage } from './pages/admin/DataRequestsPage'
import { ModelBenchPage } from './pages/admin/ModelBenchPage'
import { ClaimsPage } from './pages/claims/ClaimsPage'
import { SettingsPage } from './pages/admin/SettingsPage'
import { StaffManagementPage } from './pages/admin/StaffManagementPage'
import { AnalyticsPage } from './pages/analytics/AnalyticsPage'
import { ClientProfilePage } from './pages/clients/ClientProfilePage'
import { ClientsPage } from './pages/clients/ClientsPage'
import { EscalationsPage } from './pages/escalations/EscalationsPage'
import { HomePage } from './pages/home/HomePage'
import { ClientSignInPage } from './pages/intake/ClientSignInPage'
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
 *   /auth                  The team sign-in. Clients sign in at /portal.
 *   /auth/register-carrier Onboard a carrier. Deliberately linked from nowhere.
 *   /portal                Client portal. Its own sign-in and cookie, so it is
 *                          not behind ProtectedRoute; it sends itself back to
 *                          the client sign-in when there is no portal session.
 *
 * Guarded by ProtectedRoute -> AppLayout (the console):
 *   /queue                 Queue - role-tailored view
 *   /clients               Every applicant, with their latest application
 *   /analytics             The company's book, in numbers and charts
 *   /escalations           Escalation inbox. Doctor and Administrator only
 *   /admin/users           Team accounts. Administrator only
 *   /admin/settings        Company settings. Administrator only
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
        <Route path="/queue" element={<NotForDoctors><QueuePage /></NotForDoctors>} />
        <Route path="/clients" element={<ClientsPage />} />
        <Route path="/clients/:id" element={<ClientProfilePage />} />
        <Route path="/analytics" element={<OwnerOnly screen="analytics"><AnalyticsPage /></OwnerOnly>} />
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
        <Route
          path="/data-requests"
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <DataRequestsPage />
            </ProtectedRoute>
          }
        />
        <Route path="/claims" element={<NotForDoctors><ClaimsPage /></NotForDoctors>} />
        <Route
          path="/model-bench"
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <ModelBenchPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/access-requests"
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <AccessRequestsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/settings"
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <SettingsPage />
            </ProtectedRoute>
          }
        />
        <Route path="/applications/new" element={<NotForDoctors><IntakePage /></NotForDoctors>} />
        <Route path="/applications/:id/sign-in" element={<NotForDoctors><ClientSignInPage /></NotForDoctors>} />
        <Route path="/applications/:id" element={<ReviewPage />} />
        <Route path="/notifications" element={<NotificationsPage />} />
        <Route path="/pricing" element={<OwnerOnly screen="pricing"><PricingPage /></OwnerOnly>} />
        <Route path="/profile" element={<ProfilePage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
