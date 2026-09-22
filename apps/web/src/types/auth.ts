/**
 * The three staff roles. There are no others.
 *
 * Applicants are not here on purpose: they have no account and no role. They
 * read their own application in the client portal with a generated portal ID
 * and password.
 *
 * `medical_professional` was `senior_underwriter` until 2026-09-22. What it
 * may do did not change.
 */
export type UserRole = 'underwriter' | 'medical_professional' | 'admin'

/** How each role is named on screen. One place, so the screens cannot disagree. */
export const ROLE_LABEL: Record<UserRole, string> = {
  underwriter: 'Underwriter',
  medical_professional: 'Medical Professional',
  admin: 'Administrator',
}

export interface User {
  id: string
  tenantId: string
  fullName: string
  email: string
  role: UserRole
  licenseNumber?: string | null
  createdAt: string
  isActive?: boolean
  lastLoginAt?: string | null
}

export interface Tenant {
  id: string
  name: string
  subscriptionTier: string
  createdAt: string
}

export interface LoginPayload {
  email: string
  password: string
}

export interface RegisterTenantPayload {
  tenantName: string
  subscriptionTier: string
  adminFullName: string
  adminEmail: string
  adminPassword: string
  licenseNumber?: string
  role?: UserRole
}

export interface AuthResponse {
  user: User
  tenant: Tenant
}
