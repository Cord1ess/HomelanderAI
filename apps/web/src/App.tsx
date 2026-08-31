import { Navigate, Route, Routes } from 'react-router-dom'

import { RequireAuth } from './auth/AuthContext'
import { AppLayout } from './pages/layout/AppLayout'
import { HomePage } from './pages/home/HomePage'
import { IntakePage } from './pages/intake/IntakePage'
import { LoginPage } from './pages/login/LoginPage'
import { NotificationsPage } from './pages/notifications/NotificationsPage'
import { QueuePage } from './pages/queue/QueuePage'
import { ReviewPage } from './pages/review/ReviewPage'

/**
 * Routes.
 *
 * Public:
 *   /                      Home landing (Hero + sign-in CTA)
 *   /login                 email + password
 *
 * Guarded by RequireAuth → AppLayout (the ERP console):
 *   /queue                 Queue — all applications, filterable
 *   /applications/new      Intake form
 *   /applications/:id      Review workspace
 *   /notifications         Notification list
 *
 * Requires sign-in because of the health data; /login lives outside the guard.
 */
export function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route path="/queue" element={<QueuePage />} />
        <Route path="/applications/new" element={<IntakePage />} />
        <Route path="/applications/:id" element={<ReviewPage />} />
        <Route path="/notifications" element={<NotificationsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
