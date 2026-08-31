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
      // Session will be an httpOnly cookie, so credentials must ride along.
      credentials: 'include',
      headers: { Accept: 'application/json', ...init?.headers },
      ...init,
    })
  } catch {
    // fetch only rejects on network-level failure — most often "API not running".
    throw new ApiError(0, 'Could not reach the API. Is it running on port 8000?')
  }

  if (!response.ok) {
    let errorDetail = `${response.status} ${response.statusText}`
    try {
      const errJson = await response.json()
      if (errJson?.detail) {
        if (typeof errJson.detail === 'string') {
          errorDetail = errJson.detail
        } else if (Array.isArray(errJson.detail)) {
          errorDetail = errJson.detail.map((d: { msg?: string }) => d.msg || JSON.stringify(d)).join(', ')
        }
      }
    } catch {
      // ignore json parse error
    }
    throw new ApiError(response.status, errorDetail)
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

