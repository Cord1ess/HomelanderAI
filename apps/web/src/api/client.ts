import type { components } from './schema'
import type { AuthResponse, LoginPayload, RegisterTenantPayload } from '../types/auth'

/**
 * API client.
 *
 * Response types are **generated** from the API's own OpenAPI document, not
 * hand-written — that is what stops the two halves of the project drifting
 * apart. Regenerate after any change to a FastAPI response model:
 *
 *     npm run gen:api        (API must be running)
 */

type Schemas = components['schemas']

export type Queue = Schemas['QueueSchema']
export type QueueItem = Schemas['QueueItemSchema']
export type ApplicationDetail = Schemas['ApplicationDetailSchema']
export type ApplicationStatus = Schemas['ApplicationStatus']
export type Finding = Schemas['FindingSchema']
export type Adjustment = Schemas['AdjustmentSchema']
export type EvidenceFile = Schemas['FileSchema']
export type Decision = Schemas['DecisionSchema']
export type DecisionType = Schemas['UnderwriterDecisionType']
export type AuditTrail = Schemas['AuditTrailSchema']
export type AppNotification = Schemas['NotificationSchema']
export type SubmitResponse = Schemas['SubmitResponseSchema']

// Relative, so the Vite dev proxy handles it and the production build works
// from whatever origin serves the bundle.
const BASE_URL = '/api'

export class ApiError extends Error {
  // Declared explicitly rather than as a constructor parameter property:
  // the tsconfig enables `erasableSyntaxOnly`, which forbids syntax that emits
  // runtime code.
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response

  try {
    response = await fetch(`${BASE_URL}${path}`, {
      // The session is an httpOnly cookie, so credentials must ride along.
      credentials: 'include',
      headers: { Accept: 'application/json', ...init?.headers },
      ...init,
    })
  } catch {
    // fetch only rejects on network-level failure — most often "API not running".
    throw new ApiError(0, 'Could not reach the API. Is it running on port 8000?')
  }

  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response))
  }

  return (await response.json()) as T
}

/** FastAPI puts a string in `detail` for our errors and an array for validation ones. */
async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json()
    const detail = body?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join(', ')
    }
  } catch {
    // Not JSON — fall through to the status line.
  }
  return `${response.status} ${response.statusText}`
}

// ── health ───────────────────────────────────────────────────────────────────

export type HealthResponse = Schemas['HealthResponse']

export const getHealth = () => request<HealthResponse>('/health')

// ── auth ─────────────────────────────────────────────────────────────────────

export const login = (payload: LoginPayload) =>
  request<AuthResponse>('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

export const registerTenant = (payload: RegisterTenantPayload) =>
  request<AuthResponse>('/auth/register-tenant', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

export const getCurrentUser = () => request<AuthResponse>('/auth/me')

export const logout = () => request<{ status: 'ok' }>('/auth/logout', { method: 'POST' })

// ── applications ─────────────────────────────────────────────────────────────

export function getQueue(params: { status?: string; q?: string } = {}) {
  const search = new URLSearchParams()
  if (params.status && params.status !== 'all') search.set('status', params.status)
  if (params.q?.trim()) search.set('q', params.q.trim())

  const query = search.toString()
  return request<Queue>(`/applications${query ? `?${query}` : ''}`)
}

export const getApplication = (id: string) => request<ApplicationDetail>(`/applications/${id}`)

export interface IntakePayload {
  applicant: {
    name: string
    phone: string
    dateOfBirth: string | null
    sex: string | null
  }
  coverage: {
    coverageType: string | null
    coverageAmount: number | null
    policyTerm: string | null
  }
  modelsRequested: string[]
  declaredHistory: Record<string, unknown>
}

/**
 * Submit an application with its evidence.
 *
 * multipart, because files and structured data travel together. The JSON goes
 * in a single `payload` field rather than being flattened into form fields —
 * `declaredHistory` is nested, and flattening it would mean encoding and
 * decoding a shape that already has a perfectly good representation.
 *
 * `files` and `fileArms` are parallel: `fileArms[i]` names the model arm that
 * `files[i]` belongs to. FormData preserves the order of repeated fields, so
 * the pairing survives the round trip.
 */
export function submitApplication(input: {
  payload: IntakePayload
  files: { file: File; arm: string }[]
  facePhoto?: File | null
}): Promise<SubmitResponse> {
  const form = new FormData()
  form.append('payload', JSON.stringify(input.payload))

  for (const { file, arm } of input.files) {
    form.append('files', file)
    form.append('file_arms', arm)
  }

  if (input.facePhoto) form.append('face_photo', input.facePhoto)

  // No Content-Type header: the browser has to set it, because only it knows
  // the multipart boundary.
  return request<SubmitResponse>('/applications', { method: 'POST', body: form })
}

export const recordDecision = (
  id: string,
  body: { decision: DecisionType; finalPremium?: number | null },
) =>
  request<Decision>(`/applications/${id}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

export const getAuditTrail = (id: string) => request<AuditTrail>(`/applications/${id}/audit`)

/** Images are served by the API, not from a static folder, so each read is
 * checked against the caller's tenant. */
export const fileUrl = (id: string) => `${BASE_URL}/files/${id}`

// ── notifications ────────────────────────────────────────────────────────────

export const getNotifications = () => request<AppNotification[]>('/notifications')

export const markNotificationRead = (id: string) =>
  request<AppNotification>(`/notifications/${id}/read`, { method: 'POST' })
