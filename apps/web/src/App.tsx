import { Navigate, Route, Routes } from 'react-router-dom'

import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { AuthPage } from './pages/AuthPage'
import { HomePage } from './pages/home/HomePage'
import { IntakePage } from './pages/intake/IntakePage'
import { AppLayout } from './pages/layout/AppLayout'
import { NotificationsPage } from './pages/notifications/NotificationsPage'
import { PricingPage } from './pages/pricing/PricingPage'
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
 *   /queue                 Queue - all applications, filterable
 *   /applications/new      Intake form
 *   /applications/:id      Review workspace
 *   /notifications         Notification list
 *   /pricing               Plan and premium per risk tier
 *
 * Sign-in is required for the console because it shows health data.
 *
 * The router and the auth provider both live in main.tsx, so there is exactly
 * one of each. This file only maps paths to screens.
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
        <Route path="/applications/new" element={<IntakePage />} />
        <Route path="/applications/:id" element={<ReviewPage />} />
        <Route path="/notifications" element={<NotificationsPage />} />
        <Route path="/pricing" element={<PricingPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
