import type { AuthResponse, LoginPayload, RegisterTenantPayload } from '../types/auth'

/**
 * Minimal API client.
 *
 * Hand-written types for now. Once the API has real endpoints, replace these
 * with generated ones:
 *
 *     npm run gen:api        (API must be running)
 *
 * and import from `./schema` instead of declaring interfaces here.
 */

// Relative, so the Vite dev proxy handles it and the production build works
// from whatever origin serves the bundle.
const BASE_URL = '/api'


export class ApiError extends Error {
  // Declared explicitly rather than as a constructor parameter property:
  // the tsconfig enables `erasableSyntaxOnly`, which forbids syntax that emits
  // runtime code.
  readonly status: number

  constructor(status: number, message: string, options?: ErrorOptions) {
    super(message, options)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response

  try {
    response = await fetch(`${BASE_URL}${path}`, {
      // Session will be an httpOnly cookie, so credentials must ride along.
      credentials: 'include',
      headers: { Accept: 'application/json', ...init?.headers },
      ...init,
    })
  } catch (cause) {
    // fetch only rejects on network-level failure — most often "API not running".
    throw new ApiError(0, 'Could not reach the API. Is it running on port 8000?', { cause })
  }

  if (!response.ok) {
    throw new ApiError(response.status, `${response.status} ${response.statusText}`)
  }

  return (await response.json()) as T
}


export interface HealthResponse {
  status: 'ok'
  service: string
  version: string
  environment: string
  uptime_seconds: number
}

export const getHealth = () => request<HealthResponse>('/health')

// Auth API methods
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

export const logout = () =>
  request<{ status: 'ok' }>('/auth/logout', {
    method: 'POST',
  })

