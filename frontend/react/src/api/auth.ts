import apiClient from './client'
import type { UserRole } from '@/store/auth'

export interface LoginRequest {
  email: string
  password: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user_id: string
  role: UserRole
}

export type InstitutionType =
  | 'commercial_bank'
  | 'investment_bank'
  | 'insurance'
  | 'leasing'
  | 'microfinance'
  | 'other'

export interface RegisterRequest {
  full_name: string
  email: string
  password: string
  institution_name: string
  institution_type: InstitutionType
}

export async function login(data: LoginRequest): Promise<AuthResponse> {
  const res = await apiClient.post<AuthResponse>('/api/v1/auth/login', data)
  return res.data
}

export async function register(data: RegisterRequest): Promise<AuthResponse> {
  const res = await apiClient.post<AuthResponse>('/api/v1/auth/register', data)
  return res.data
}

export function logout(): void {
  localStorage.removeItem('esg_token')
  window.location.replace('/auth/login')
}