# Dashboard Implementation

How the authenticated dashboard connects to the API, how login behaves, and
how the session-expired state works. This is the contract the frontend
(`apps/web`) is built against; the auth endpoints themselves ship later (only
`/api/health` exists in Phase 0, so the app currently runs on an in-memory mock).

## Current state (Phase 0)

- Auth is **frontend-only and in-memory**.
  - `src/auth/AuthContext.tsx` holds `{ user, signIn, signOut }` in React state.
  - Nothing is persisted — no `localStorage`/`sessionStorage`. A refresh drops
    the session and the `RequireAuth` guard bounces you back to `/login`.
  - This respects DASHBOARD.md's "no token in JS" rule in spirit: no credential
    or token ever reaches JavaScript during normal operation.
- `src/auth/AuthContext.tsx`'s `RequireAuth` wraps the console routes. The public
  routes (`/`, `/login`) are outside the guard.

### Routes

| Path              | Public | Page                                   |
| ----------------- | ------ | -------------------------------------- |
| `/`               | yes    | Home landing (Hero + sign-in CTA)      |
| `/login`          | yes    | Email + password                        |
| `/queue`          | no     | Review queue (guarded)                 |
| `/applications/new` | no   | Intake form (guarded)                  |
| `/applications/:id` | no   | Review workspace (guarded)             |
| `/notifications`  | no     | Notification list (guarded)            |

Requiring sign-in is deliberate: the console shows health/treatment data.

## API connection

The web client is generated against the backend (see DASHBOARD.md):
`npm run gen:api` (run with the API running) regenerates the typed client used
by the dashboard.

Define a tenant resolver against the RLS model (DATABASE.md) — every row read or
written is tenant-scoped, so the client should never guess ids across tenants.

## Login behavior

The frontend uses `POST /api/auth/login` with email + password:

1. **Login** — `POST /api/auth/login { email, password }`. On success the server
   sets an **httpOnly cookie**. The token never reaches JavaScript.
2. **Confirm identity** — `GET /api/auth/me` returns `{ user, tenant, role }`.
   Seed the in-memory session with this so the shell can show who is signed in
   and which tenant scopes the requests.
3. **Navigate** — land on `/queue`.
4. **Logout** — `POST /api/auth/logout` clears the cookie; `signOut()` clears the
   in-memory session and the shell returns to `/`.

Login screen behavior (LoginPage.tsx):

- Email + password **only**. No signup, no reset, no SSO.
- Emptiness / missing-field error is shown inline without the need for an
  external validator (the form gates on `!email || !password`).
- While logged in progress (in-flight) the submit button is `loading`/`disabled`
  so double-submits can't occur.
- On success → `/queue`.

### Mock swap (TODO)

Until the endpoints exist, `signIn()` just records the email locally and
`LoginPage` navigates after a short delay. When the backend arrives:

- Replace the mock in `LoginPage`'s submit with the real `POST` + `GET /me`.
- Replace `AuthContext.signIn`'s hard-coded `{ role: 'underwriter', tenant:
  'demo-carrier' }` with the `GET /api/auth/me` payload.

## Session-expired state

A session goes stale either because the cookie expired or a refresh dropped the
in-memory session.

### 401 interception

Any guarded API call that returns `401` should conclude the session:

1. `signOut()` to clear local state.
2. Navigate to `/login?expired=1`.

The `RequireAuth` guard already redirects to `/login?expired=1` (`replace`) when
it finds no session, so a mid-console refresh is handled without an API round trip.

### UI

`LoginPage` reads `?expired=1` from the URL and renders a yellow
"Your session has expired — sign in again" banner above the form. A plain visit
to `/login` (no query param) shows no banner.

## Files

- `src/auth/AuthContext.tsx` — `AuthProvider`, `useAuth`, `RequireAuth`, session
  shape, and the mock→real TODO markers.
- `src/App.tsx` — route table (public + guarded).
- `src/pages/login/LoginPage.tsx` — login form, `?expired=1` banner, navigation.
- `src/pages/layout/AppLayout.tsx` — shell sign-out → `signOut()` → Home.
