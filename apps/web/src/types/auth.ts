export type UserRole = 'underwriter' | 'senior_underwriter' | 'admin'

export interface User {
  id: string
  tenantId: string
  fullName: string
  email: string
  role: UserRole
  licenseNumber?: string | null
  createdAt: string
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
