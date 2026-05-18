import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type UserRole = 'company' | 'consultant' | 'admin' | 'company_admin'

interface AuthState {
  token: string | null
  userId: string | null
  email: string | null
  role: UserRole
  setAuth: (token: string, userId: string, role?: UserRole, email?: string) => void
  clearAuth: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      userId: null,
      email: null,
      role: 'company_admin',
      setAuth: (token, userId, role = 'company_admin', email) => {
        localStorage.setItem('esg_token', token)
        set({ token, userId, role, email: email ?? null })
      },
      clearAuth: () => {
        localStorage.removeItem('esg_token')
        set({ token: null, userId: null, email: null, role: 'company_admin' })
      },
    }),
    { name: 'esg-auth' },
  ),
)

/** Derive a short display handle from email: "john.doe@bank.com" → "john.doe" */
export function emailHandle(email: string | null): string {
  if (!email) return 'User'
  return email.split('@')[0]
}

/** Two-letter initials from email local part: "john.doe" → "JD", "ahmed" → "AH" */
export function emailInitials(email: string | null): string {
  if (!email) return 'U'
  const local = email.split('@')[0]
  const parts = local.split(/[._\-+]/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return local.slice(0, 2).toUpperCase()
}
