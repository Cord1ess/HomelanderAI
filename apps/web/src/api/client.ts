import type { components } from './schema'
import type { AuthResponse, LoginPayload, RegisterTenantPayload, UserRole } from '../types/auth'

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
export type Plan = Schemas['PlanSchema']
export type ModelInfo = Schemas['ModelSchema']
export type Pricing = Schemas['PricingSchema']
export type ClassifiedFile = Schemas['ClassifiedFileSchema']
export type ClassifyResponse = Schemas['ClassifyResponseSchema']
export type RequestedDocument = Schemas['RequestedDocumentSchema']
export type TenantSettings = Schemas['TenantSettingsSchema']
export type SubmitResponse = Schemas['SubmitResponseSchema']
export type PortalStatus = Schemas['PortalStatusSchema']
export type Client = Schemas['ClientSchema']
export type Analytics = Schemas['AnalyticsSchema']
export type PortalCredentials = Schemas['PortalCredentialsSchema']
export type ArmRun = Schemas['ArmRunSchema']

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

export const updateProfile = (payload: { fullName?: string; licenseNumber?: string }) =>
  request<AuthResponse['user']>('/auth/profile', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

export const changePassword = (payload: { currentPassword: string; newPassword: string }) =>
  request<{ status: 'ok' }>('/auth/profile/change-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

export const getStaffUsers = () => request<AuthResponse['user'][]>('/auth/users')

/** Admin only. A deactivated account keeps its history and cannot sign in. */
export const setStaffStatus = (userId: string, isActive: boolean) =>
  request<AuthResponse['user']>(`/auth/users/${userId}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ isActive }),
  })

export const provisionStaffUser = (payload: {
  fullName: string
  email: string
  password: string
  role: UserRole
  licenseNumber?: string
}) =>
  request<AuthResponse['user']>('/auth/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

// ── applications ─────────────────────────────────────────────────────────────

export function getQueue(params: { status?: string; q?: string } = {}) {
  const search = new URLSearchParams()
  if (params.status && params.status !== 'all') search.set('status', params.status)
  if (params.q?.trim()) search.set('q', params.q.trim())

  const query = search.toString()
  return request<Queue>(`/applications${query ? `?${query}` : ''}`)
}

export const getApplication = (id: string) => request<ApplicationDetail>(`/applications/${id}`)

/**
 * Which models the intake form may offer, and which of them actually run.
 *
 * `available` is derived on the server from the arm registry, so the form can
 * never present a model that would silently produce no score.
 */
export const getModels = () => request<ModelInfo[]>('/models')

/**
 * Work out what each dropped file is, before anything is submitted.
 *
 * Stores nothing and creates no application: this runs while the operator is
 * still filling in the form, so the review screen is instant when they submit.
 * What comes back is a proposal the operator confirms or corrects.
 */
export function classifyEvidence(files: File[]): Promise<ClassifyResponse> {
  const form = new FormData()
  for (const file of files) form.append('files', file)
  return request<ClassifyResponse>('/evidence/classify', { method: 'POST', body: form })
}

/**
 * The plan for every tier, priced for a given sum assured.
 *
 * The rates and the tier cut-points both come from the API — the dashboard must
 * not keep its own copy, or the two drift and a screen quotes a premium against
 * the wrong band.
 */
export const getPricing = (coverage?: number | null) =>
  request<Pricing>(`/pricing${coverage ? `?coverage=${coverage}` : ''}`)

export interface IntakePayload {
  applicant: {
    name: string
    phone: string
    dateOfBirth: string | null
    sex: string | null
    /** Where the client's portal sign-in is sent. Without it the operator is shown it. */
    email: string | null
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
  files: { file: File; arm: string; kind: string }[]
  facePhoto?: File | null
}): Promise<SubmitResponse> {
  const form = new FormData()
  form.append('payload', JSON.stringify(input.payload))

  // `files`, `file_arms` and `file_kinds` are parallel. FormData preserves the
  // order of repeated fields, so the three stay paired across the round trip.
  // `file_kinds` is what the operator confirmed on the review screen, and it is
  // what decides which model reads each file.
  for (const { file, arm, kind } of input.files) {
    form.append('files', file)
    form.append('file_arms', arm)
    form.append('file_kinds', kind)
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

/**
 * Ask the applicant for specific documents, in the underwriter's own words.
 *
 * This is a pause, not a decision: decisions are write-once, so recording a
 * request there would decide the application forever the moment a document
 * was asked for. The application moves to `awaiting_evidence` and the decision
 * stays open.
 */
export const requestEvidence = (id: string, body: { items: string[]; note?: string | null }) =>
  request<RequestedDocument[]>(`/applications/${id}/evidence-request`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

/**
 * Move the date the applicant was told to expect an answer by.
 *
 * A reason is required and is shown to the applicant: a date that moves with
 * no explanation is exactly the silent slip this replaces.
 */
export const reviseTurnaround = (id: string, body: { expectedBy: string; reason: string }) =>
  request<ApplicationDetail>(`/applications/${id}/turnaround`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

// ── tenant settings ──────────────────────────────────────────────────────────

export const getTenantSettings = () => request<TenantSettings>('/tenant/settings')

export type TenantSettingsUpdate = Schemas['TenantSettingsIn']
export type SettingsChange = Schemas['SettingsChangeSchema']

/**
 * Admin only. A partial update: only the fields sent change. Applies from now
 * on; dates already promised and scores already computed are not moved.
 */
export const updateTenantSettings = (body: TenantSettingsUpdate) =>
  request<TenantSettings>('/tenant/settings', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

/** Who changed which setting, from what. Newest first. */
export const getTenantSettingsHistory = () => request<SettingsChange[]>('/tenant/settings/history')

/**
 * Hand the application to a medical professional. Not a decision: the decision
 * stays open and becomes theirs. Every medical professional is told.
 */
export const escalateApplication = (id: string, body: { note?: string | null } = {}) =>
  request<ApplicationDetail>(`/applications/${id}/escalate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

/**
 * Tick off one requested document as received, attaching the document itself
 * when it is in hand. The file is stored with the application and linked to
 * the request. Idempotent.
 */
export const fulfilEvidenceRequest = (id: string, documentId: string, file?: File | null) => {
  const body = new FormData()
  if (file) body.append('file', file)
  return request<RequestedDocument>(`/applications/${id}/evidence-request/${documentId}/fulfil`, {
    method: 'POST',
    body,
  })
}

/** Images are served by the API, not from a static folder, so each read is
 * checked against the caller's tenant. */
export const fileUrl = (id: string) => `${BASE_URL}/files/${id}`

// ── notifications ────────────────────────────────────────────────────────────

export const getNotifications = () => request<AppNotification[]>('/notifications')

export const markNotificationRead = (id: string) =>
  request<AppNotification>(`/notifications/${id}/read`, { method: 'POST' })

// ── clients and analytics ────────────────────────────────────────────────────

export const getClients = (q?: string) =>
  request<Client[]>(`/clients${q ? `?q=${encodeURIComponent(q)}` : ''}`)

export const getAnalytics = () => request<Analytics>('/analytics')

// ── client portal ────────────────────────────────────────────────────────────
//
// A separate sign-in from the staff console, with its own cookie. The response
// type has no field for a score or a finding, so there is nothing clinical for
// this side of the app to render by mistake.

export const portalLogin = (body: { portalId: string; password: string }) =>
  request<PortalStatus>('/portal/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

export const getPortalStatus = () => request<PortalStatus>('/portal/me')

export const portalLogout = () => request<{ status: 'ok' }>('/portal/logout', { method: 'POST' })
