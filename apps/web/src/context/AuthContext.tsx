import { notifications } from '@mantine/notifications'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, type ReactNode, useContext } from 'react'
import { getCurrentUser, login as loginApi, logout as logoutApi, registerTenant as registerTenantApi } from '../api/client'
import type { AuthResponse, LoginPayload, RegisterTenantPayload, Tenant, User } from '../types/auth'

interface AuthContextType {
  user: User | null
  tenant: Tenant | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (payload: LoginPayload) => Promise<void>
  registerTenant: (payload: RegisterTenantPayload) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()

  // Session check on mount / refetch
  const { data, isLoading } = useQuery<AuthResponse | null>({
    queryKey: ['auth', 'me'],
    queryFn: async () => {
      try {
        return await getCurrentUser()
      } catch {
        return null
      }
    },
    staleTime: 1000 * 60 * 5, // 5 mins
    retry: false,
  })

  // Login mutation
  const loginMutation = useMutation({
    mutationFn: loginApi,
    onSuccess: (res) => {
      queryClient.setQueryData(['auth', 'me'], res)
      notifications.show({
        title: 'Welcome back',
        message: `Signed in as ${res.user.fullName} (${res.tenant.name})`,
        color: 'teal',
      })
    },
  })

  // Register mutation
  const registerMutation = useMutation({
    mutationFn: registerTenantApi,
    onSuccess: (res) => {
      queryClient.setQueryData(['auth', 'me'], res)
      notifications.show({
        title: 'Account created',
        message: `${res.tenant.name} is set up. You are signed in as ${res.user.fullName}.`,
        color: 'teal',
      })
    },
  })

  // Logout mutation
  const logoutMutation = useMutation({
    mutationFn: logoutApi,
    onSuccess: () => {
      queryClient.setQueryData(['auth', 'me'], null)
      notifications.show({
        title: 'Signed out',
        message: 'You have been signed out.',
        color: 'blue',
      })
    },
    onError: () => {
      // Clear session even if API logout call fails
      queryClient.setQueryData(['auth', 'me'], null)
    },
  })

  const login = async (payload: LoginPayload) => {
    try {
      await loginMutation.mutateAsync(payload)
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Invalid login credentials'
      notifications.show({
        title: 'Sign In Failed',
        message: errorMsg,
        color: 'red',
      })
      throw err
    }
  }

  const registerTenant = async (payload: RegisterTenantPayload) => {
    try {
      await registerMutation.mutateAsync(payload)
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Registration failed'
      notifications.show({
        title: 'Could not create the account',
        message: errorMsg,
        color: 'red',
      })
      throw err
    }
  }

  const logout = async () => {
    try {
      await logoutMutation.mutateAsync()
    } catch {
      queryClient.setQueryData(['auth', 'me'], null)
    }
  }

  return (
    <AuthContext.Provider
      value={{
        user: data?.user ?? null,
        tenant: data?.tenant ?? null,
        isAuthenticated: Boolean(data?.user),
        isLoading,
        login,
        registerTenant,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
