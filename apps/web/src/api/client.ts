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
export type Quote = Schemas['QuoteSchema']
export type ClassifiedFile = Schemas['ClassifiedFileSchema']
export type ClassifyResponse = Schemas['ClassifyResponseSchema']
export type RequestedDocument = Schemas['RequestedDocumentSchema']
export type TenantSettings = Schemas['TenantSettingsSchema']
export type SubmitResponse = Schemas['SubmitResponseSchema']
export type PortalStatus = Schemas['PortalStatusSchema']
export type Client = Schemas['ClientSchema']
export type ClientProfile = Schemas['ClientProfileSchema']
export type Analytics = Schemas['AnalyticsSchema']
export type PortalCredentials = Schemas['PortalCredentialsSchema']
export type ArmRun = Schemas['ArmRunSchema']
export type AccessRequest = Schemas['AccessRequestSchema']
export type Policy = Schemas['PolicySchema']
export type Claim = Schemas['ClaimSchema']
export type PortalClaim = Schemas['PortalClaimSchema']
export type Deletion = Schemas['DeletionSchema']
export type NidRead = Schemas['NidReadSchema']
export type ClientSignIn = Schemas['ClientSignInSchema']
export type EmailLogEntry = Schemas['EmailLogSchema']
export type MailStatus = Schemas['MailStatusSchema']
export type BenchResult = Schemas['BenchResultSchema']
export type BenchRun = Schemas['BenchRunSchema']
export type Business = Schemas['BusinessSchema']
export type ClaimAction = Schemas['ClaimActionIn']['action']

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

export function getQueue(params: { status?: string; q?: string; mine?: boolean } = {}) {
  const search = new URLSearchParams()
  if (params.status && params.status !== 'all') search.set('status', params.status)
  if (params.mine) search.set('mine', 'true')
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
export const getPricing = () => request<Pricing>('/pricing')

/** Price one policy from the facts, before there is an application. */
export const quote = (body: {
  product: 'life' | 'health'
  sumAssuredBdt: number
  termYears?: number
  dateOfBirth?: string | null
  age?: number | null
  sex?: string | null
  smoker?: boolean
  ratingPct?: number
}) =>
  request<Quote>('/quote', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

/** Price an application's cover at a rating. */
export const quoteApplication = (id: string, ratingPct: number) =>
  request<Quote>(`/applications/${id}/quote`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ratingPct }),
  })

/** Read the front of an NID card: name, date of birth, number. Stores nothing. */
export function readNid(image: File): Promise<NidRead> {
  const form = new FormData()
  form.append('image', image)
  return request<NidRead>('/nid/read', { method: 'POST', body: form })
}

/** Take a case (or hand it back), so two underwriters do not work it at once. */
export const assignApplication = (id: string, release = false) =>
  request<ApplicationDetail>(`/applications/${id}/assign${release ? '?release=true' : ''}`, {
    method: 'POST',
  })

export interface IntakePayload {
  applicant: {
    name: string
    phone: string
    dateOfBirth: string | null
    sex: string | null
    /** Where the client's portal sign-in is sent. Without it the operator is shown it. */
    email: string | null
    nidNumber?: string | null
    nidName?: string | null
    nidDateOfBirth?: string | null
    nomineeName?: string | null
    nomineeRelation?: string | null
    nomineePhone?: string | null
    consent: boolean
  }
  coverage: {
    coverageType: string | null
    coverageAmount: number | null
    policyTerm: string | null
    paymentMode: 'monthly' | 'yearly'
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
  nidImage?: File | null
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
  if (input.nidImage) form.append('nid_image', input.nidImage)

  // No Content-Type header: the browser has to set it, because only it knows
  // the multipart boundary.
  return request<SubmitResponse>('/applications', { method: 'POST', body: form })
}

export const recordDecision = (
  id: string,
  body: {
    decision: DecisionType
    ratingPct?: number
    exclusions?: string[]
    declineReason?: string | null
    declineNote?: string | null
    reapplyAfterMonths?: number | null
  },
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
 * Hand the application to a doctor. Not a decision: the decision
 * stays open and becomes theirs. Every doctor is told.
 */
/** A doctor returns the application to the underwriter with a verdict on the results. */
export const reviewAsDoctor = (
  id: string,
  body: { verdict: 'accurate' | 'inaccurate'; note?: string | null },
) =>
  request<ApplicationDetail>(`/applications/${id}/doctor-review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

/** A doctor writes to the client directly; it appears on their portal. */
export const messageClient = (
  id: string,
  body: { urgency: 'urgent' | 'routine'; message: string },
) =>
  request<ApplicationDetail>(`/applications/${id}/client-message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

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
export const markAllNotificationsRead = () =>
  request<{ updated: number }>('/notifications/read-all', { method: 'POST' })

// ── clients and analytics ────────────────────────────────────────────────────

export const getClients = (q?: string) =>
  request<Client[]>(`/clients${q ? `?q=${encodeURIComponent(q)}` : ''}`)
export const getClient = (id: string) => request<ClientProfile>(`/clients/${id}`)

export const getAnalytics = () => request<Analytics>('/analytics')

// ── asking to see a client's details ─────────────────────────────────────────

/** An underwriter or a doctor asks the owner to see one client's details. */
export const requestClientAccess = (clientId: string, reason: string) =>
  request<AccessRequest>(`/clients/${clientId}/access-requests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  })

/** Every request for an administrator; your own for anyone else. */
export const getAccessRequests = () => request<AccessRequest[]>('/access-requests')

export const decideAccessRequest = (id: string, approve: boolean) =>
  request<AccessRequest>(`/access-requests/${id}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approve }),
  })

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

/** The client uploads a document they were asked for. */
export const portalUpload = (documentId: string, file: File) => {
  const body = new FormData()
  body.append('file', file)
  return request<PortalStatus>(`/portal/documents/${documentId}/upload`, { method: 'POST', body })
}

// ── policies ─────────────────────────────────────────────────────────────────

export const getPolicies = () => request<Policy[]>('/policies')

export const cancelPolicy = (id: string, reason: string) =>
  request<Policy>(`/policies/${id}/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  })

// ── claims ───────────────────────────────────────────────────────────────────

export const getClaims = (status?: string) =>
  request<Claim[]>(`/claims${status ? `?status_filter=${encodeURIComponent(status)}` : ''}`)

export const getClaim = (id: string) => request<Claim>(`/claims/${id}`)

export const claimAction = (
  id: string,
  body: { action: ClaimAction; note?: string | null; approvedAmountBdt?: number | null; settlementReference?: string | null },
) =>
  request<Claim>(`/claims/${id}/action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

export interface ClaimInput {
  eventDate: string
  claimedAmountBdt: number
  description: string
  hospital?: string | null
  claimantName?: string | null
  accident?: boolean
}

/** Staff file a claim for someone (a death claim from the nominee, say). */
export function fileClaim(policyId: string, claim: ClaimInput, files: File[]): Promise<Claim> {
  const form = new FormData()
  form.append('payload', JSON.stringify(claim))
  for (const f of files) form.append('files', f)
  return request<Claim>(`/policies/${policyId}/claims`, { method: 'POST', body: form })
}

export function addClaimDocuments(claimId: string, files: File[]): Promise<Claim> {
  const form = new FormData()
  for (const f of files) form.append('files', f)
  return request<Claim>(`/claims/${claimId}/documents`, { method: 'POST', body: form })
}

export const claimDocumentUrl = (claimId: string, documentId: string) =>
  `${BASE_URL}/claims/${claimId}/documents/${documentId}`

// ── requests to delete a client's data ───────────────────────────────────────

export const getDeletionRequests = () => request<Deletion[]>('/deletion-requests')

export const decideDeletion = (id: string, body: { approve: boolean; reason?: string | null; now?: boolean }) =>
  request<Deletion>(`/deletion-requests/${id}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

// ── a client's portal sign-in, after intake ──────────────────────────────────

export const getClientSignIn = (applicationId: string) =>
  request<ClientSignIn>(`/applications/${applicationId}/client-sign-in`)

/** A new password; emailed when it can be, otherwise returned once. */
export const reissueClientSignIn = (
  applicationId: string,
  body: { email?: string | null; sendEmail: boolean },
) =>
  request<ClientSignIn>(`/applications/${applicationId}/client-sign-in`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

// ── outgoing mail ────────────────────────────────────────────────────────────

export const getMailStatus = () => request<MailStatus>('/tenant/mail')

export const sendTestMail = (to: string) =>
  request<MailStatus>('/tenant/mail/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ to }),
  })

// ── the model test bench ─────────────────────────────────────────────────────

export const tryModel = (
  modelId: string,
  input: { files: File[]; values: Record<string, unknown>; dateOfBirth?: string; sex?: string | null },
) => {
  const body = new FormData()
  for (const f of input.files) body.append('files', f)
  body.append('values', JSON.stringify(input.values))
  if (input.dateOfBirth) body.append('date_of_birth', input.dateOfBirth)
  if (input.sex) body.append('sex', input.sex)
  return request<BenchResult>(`/models/${modelId}/try`, { method: 'POST', body })
}

/** The client files a claim for hospital bills, with the bills. */
export function portalFileClaim(claim: ClaimInput, files: File[]): Promise<PortalStatus> {
  const form = new FormData()
  form.append('payload', JSON.stringify(claim))
  for (const f of files) form.append('files', f)
  return request<PortalStatus>('/portal/claims', { method: 'POST', body: form })
}

export function portalClaimDocuments(claimId: string, files: File[]): Promise<PortalStatus> {
  const form = new FormData()
  for (const f of files) form.append('files', f)
  return request<PortalStatus>(`/portal/claims/${claimId}/documents`, { method: 'POST', body: form })
}

export const portalRequestDeletion = (reason?: string | null) =>
  request<PortalStatus>('/portal/deletion-request', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason: reason ?? null }),
  })

export const portalWithdrawDeletion = () =>
  request<PortalStatus>('/portal/deletion-request', { method: 'DELETE' })
