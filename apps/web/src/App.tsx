import { Navigate, Route, Routes } from 'react-router-dom'

import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { AuthPage } from './pages/AuthPage'
import { StaffManagementPage } from './pages/admin/StaffManagementPage'
import { EscalationsPage } from './pages/escalations/EscalationsPage'
import { HomePage } from './pages/home/HomePage'
import { IntakePage } from './pages/intake/IntakePage'
import { AppLayout } from './pages/layout/AppLayout'
import { NotificationsPage } from './pages/notifications/NotificationsPage'
import { PricingPage } from './pages/pricing/PricingPage'
import { ProfilePage } from './pages/profile/ProfilePage'
import { QueuePage } from './pages/queue/QueuePage'
import { ReviewPage } from './pages/review/ReviewPage'

/**
 * Routes.
 *
 * Public:
 *   /                      Home landing (hero + sign-in CTA)
 *   /auth                  Sign in / register a carrier
 *
 * Guarded by ProtectedRoute -> AppLayout (the console):
 *   /queue                 Queue - role-tailored view
 *   /escalations           Senior Underwriter escalation inbox (unique)
 *   /admin/users           Carrier staff & operator governance (unique)
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
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/queue" element={<QueuePage />} />
        <Route path="/escalations" element={<EscalationsPage />} />
        <Route path="/admin/users" element={<StaffManagementPage />} />
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
