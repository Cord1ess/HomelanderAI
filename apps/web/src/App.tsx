import { Navigate, Route, Routes } from 'react-router-dom'

import { AppLayout } from './pages/layout/AppLayout'
import { IntakePage } from './pages/intake/IntakePage'
import { LoginPage } from './pages/login/LoginPage'
import { NotificationsPage } from './pages/notifications/NotificationsPage'
import { QueuePage } from './pages/queue/QueuePage'
import { ReviewPage } from './pages/review/ReviewPage'

/**
 * Phase 1 dashboard — five screens, per docs/DASHBOARD.md.
 *
 *   /login                email + password
 *   /                     Queue — all applications, filterable
 *   /applications/new     Intake form
 *   /applications/:id     Review workspace
 *   /notifications        Notification list
 *
 * TODO: a guard around the app layout — if `GET /api/auth/me` returns 401,
 * redirect to /login. Login sets the httpOnly cookie, so /login itself must
 * live outside the guarded layout.
 */
export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<AppLayout />}>
        <Route path="/" element={<QueuePage />} />
        <Route path="/applications/new" element={<IntakePage />} />
        <Route path="/applications/:id" element={<ReviewPage />} />
        <Route path="/notifications" element={<NotificationsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
