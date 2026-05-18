import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Users,
  Building2,
  Shield,
  RefreshCw,
  ChevronDown,
  Check,
  AlertCircle,
  Search,
} from 'lucide-react'
import apiClient from '@/api/client'
import { useAuthStore } from '@/store/auth'
import type { UserRole } from '@/store/auth'

// ─── Types ────────────────────────────────────────────────────────────────────

interface UserRecord {
  id: string
  email: string
  full_name: string
  role: UserRole
  institution_name: string
  institution_type: string
  created_at: string
}

// ─── API calls ────────────────────────────────────────────────────────────────

async function listUsers(): Promise<UserRecord[]> {
  const res = await apiClient.get<UserRecord[]>('/api/v1/admin/users')
  return res.data
}

async function updateUserRole(userId: string, role: UserRole): Promise<UserRecord> {
  const res = await apiClient.patch<UserRecord>(`/api/v1/admin/users/${userId}/role`, { role })
  return res.data
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const ROLE_META: Record<UserRole, { label: string; color: string; bg: string }> = {
  company:       { label: 'Company',       color: '#38BDF8', bg: 'rgba(56,189,248,0.12)' },
  company_admin: { label: 'Company Admin', color: '#6366F1', bg: 'rgba(99,102,241,0.12)' },
  consultant:    { label: 'Consultant',    color: '#F59E0B', bg: 'rgba(245,158,11,0.12)' },
  admin:         { label: 'Admin',         color: '#EF4444', bg: 'rgba(239,68,68,0.12)' },
}

function timeAgo(iso: string) {
  const d = (Date.now() - new Date(iso).getTime()) / 1000
  if (d < 60) return 'just now'
  if (d < 3600) return `${Math.floor(d / 60)}m ago`
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`
  return `${Math.floor(d / 86400)}d ago`
}

// ─── Role selector dropdown ───────────────────────────────────────────────────

const ALL_ROLES: UserRole[] = ['company', 'company_admin', 'consultant', 'admin']

function RoleSelector({
  userId,
  current,
  selfId,
}: {
  userId: string
  current: UserRole
  selfId: string | null
}) {
  const [open, setOpen] = useState(false)
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: (role: UserRole) => updateUserRole(userId, role),
    onSuccess: (updated) => {
      queryClient.setQueryData<UserRecord[]>(['admin-users'], (old) =>
        old ? old.map((u) => (u.id === updated.id ? updated : u)) : old,
      )
    },
  })

  const isSelf = userId === selfId
  const meta = ROLE_META[current] ?? ROLE_META.company

  return (
    <div className="relative">
      <button
        onClick={() => !isSelf && setOpen((v) => !v)}
        disabled={isSelf}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        style={{ background: meta.bg, color: meta.color }}
        title={isSelf ? "Can't change your own role" : 'Change role'}
      >
        {meta.label}
        {!isSelf && <ChevronDown size={11} />}
        {mutation.isPending && <RefreshCw size={11} className="animate-spin" />}
        {mutation.isSuccess && <Check size={11} />}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div
            className="absolute right-0 top-full mt-1 z-20 rounded-lg overflow-hidden py-1 min-w-[160px]"
            style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', boxShadow: '0 8px 24px rgba(0,0,0,0.18)' }}
          >
            {ALL_ROLES.map((r) => {
              const rm = ROLE_META[r]
              return (
                <button
                  key={r}
                  onClick={() => { mutation.mutate(r); setOpen(false) }}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-xs hover:bg-surface-raised transition-colors text-left"
                >
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ background: rm.color }}
                  />
                  <span style={{ color: r === current ? rm.color : 'var(--color-text)' }}>
                    {rm.label}
                  </span>
                  {r === current && <Check size={11} className="ml-auto" style={{ color: rm.color }} />}
                </button>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

// ─── Stats bar ────────────────────────────────────────────────────────────────

function StatsBar({ users }: { users: UserRecord[] }) {
  const byRole = (r: UserRole) => users.filter((u) => u.role === r).length
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
      {ALL_ROLES.map((r) => {
        const m = ROLE_META[r]
        const count = byRole(r)
        return (
          <div
            key={r}
            className="rounded-lg px-4 py-3 flex flex-col gap-1"
            style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
          >
            <span className="text-xs text-text-muted">{m.label}</span>
            <span className="text-2xl font-bold" style={{ color: m.color }}>{count}</span>
          </div>
        )
      })}
    </div>
  )
}

// ─── Admin page ───────────────────────────────────────────────────────────────

export default function Admin() {
  const selfId = useAuthStore((s) => s.userId)
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState<UserRole | 'all'>('all')

  const { data: users = [], isLoading, error, refetch } = useQuery({
    queryKey: ['admin-users'],
    queryFn: listUsers,
    retry: 1,
  })

  const filtered = users.filter((u) => {
    const matchRole = roleFilter === 'all' || u.role === roleFilter
    const q = search.toLowerCase()
    const matchSearch =
      !q ||
      u.email.toLowerCase().includes(q) ||
      u.full_name.toLowerCase().includes(q) ||
      u.institution_name.toLowerCase().includes(q)
    return matchRole && matchSearch
  })

  return (
    <div className="p-6 max-w-[1200px] mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Shield size={18} style={{ color: 'var(--color-primary)' }} />
            <h1 className="text-xl font-semibold text-text">Admin Console</h1>
          </div>
          <p className="text-sm text-text-muted">Manage users, roles, and institutions.</p>
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs text-text-muted hover:text-text hover:bg-surface-raised transition-colors"
          title="Refresh"
        >
          <RefreshCw size={13} />
          Refresh
        </button>
      </div>

      {/* Stats */}
      {!isLoading && !error && <StatsBar users={users} />}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        {/* Search */}
        <div
          className="flex items-center gap-2 px-3 py-2 rounded flex-1 min-w-[200px] max-w-sm"
          style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
        >
          <Search size={14} className="text-text-muted shrink-0" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search users…"
            className="flex-1 bg-transparent text-sm text-text placeholder:text-text-subtle outline-none"
          />
        </div>

        {/* Role filter */}
        <div className="flex items-center gap-1.5">
          {(['all', ...ALL_ROLES] as const).map((r) => {
            const label = r === 'all' ? 'All' : ROLE_META[r].label
            const active = roleFilter === r
            return (
              <button
                key={r}
                onClick={() => setRoleFilter(r)}
                className="px-2.5 py-1 rounded text-xs font-medium transition-colors"
                style={{
                  background: active ? 'var(--color-primary)' : 'var(--color-surface)',
                  color: active ? '#fff' : 'var(--color-text-muted)',
                  border: active ? '1px solid transparent' : '1px solid var(--color-border)',
                }}
              >
                {label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div
          className="flex items-start gap-3 px-4 py-4 rounded mb-4"
          style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)' }}
        >
          <AlertCircle size={16} style={{ color: '#EF4444' }} className="mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-medium" style={{ color: '#EF4444' }}>
              Could not load users
            </p>
            <p className="text-xs text-text-muted mt-0.5">
              The admin API endpoint may not be deployed yet. See steps below to promote your account.
            </p>
          </div>
        </div>
      )}

      {/* Table */}
      {!error && (
        <div
          className="rounded-xl overflow-hidden"
          style={{ border: '1px solid var(--color-border)' }}
        >
          <table className="w-full text-sm">
            <thead>
              <tr style={{ background: 'var(--color-surface-raised)', borderBottom: '1px solid var(--color-border)' }}>
                {['User', 'Institution', 'Role', 'Joined', ''].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-3 text-left text-xs font-semibold text-text-muted whitespace-nowrap"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading &&
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--color-border)' }}>
                    {Array.from({ length: 5 }).map((_, j) => (
                      <td key={j} className="px-4 py-3">
                        <div className="h-4 rounded animate-pulse" style={{ background: 'var(--color-surface-raised)', width: j === 1 ? '60%' : '80%' }} />
                      </td>
                    ))}
                  </tr>
                ))}
              {!isLoading &&
                filtered.map((u, i) => (
                  <tr
                    key={u.id}
                    style={{
                      background: i % 2 === 0 ? 'var(--color-surface)' : 'var(--color-bg)',
                      borderBottom: '1px solid var(--color-border)',
                    }}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        <div
                          className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
                          style={{ background: 'var(--color-primary)', color: '#fff' }}
                        >
                          {u.email.slice(0, 2).toUpperCase()}
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-text truncate">{u.full_name || u.email.split('@')[0]}</p>
                          <p className="text-xs text-text-muted truncate">{u.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <Building2 size={13} className="text-text-subtle shrink-0" />
                        <span className="text-xs text-text truncate max-w-[160px]">{u.institution_name || '—'}</span>
                      </div>
                      <p className="text-xs text-text-subtle mt-0.5">{u.institution_type?.replace(/_/g, ' ') || ''}</p>
                    </td>
                    <td className="px-4 py-3">
                      <RoleSelector userId={u.id} current={u.role} selfId={selfId} />
                    </td>
                    <td className="px-4 py-3 text-xs text-text-muted whitespace-nowrap">
                      {timeAgo(u.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      {u.id === selfId && (
                        <span className="text-xs text-text-subtle italic">you</span>
                      )}
                    </td>
                  </tr>
                ))}
              {!isLoading && filtered.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-sm text-text-subtle">
                    <Users size={20} className="mx-auto mb-2 opacity-40" />
                    No users match the current filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Admin access instructions */}
      <div
        className="mt-8 rounded-xl p-5"
        style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
      >
        <div className="flex items-center gap-2 mb-3">
          <Shield size={15} style={{ color: 'var(--color-primary)' }} />
          <p className="text-sm font-semibold text-text">How to grant admin access</p>
        </div>
        <p className="text-xs text-text-muted mb-3">
          Run the command below in a terminal to promote any registered user to admin:
        </p>
        <pre
          className="text-xs rounded-lg px-4 py-3 overflow-x-auto"
          style={{
            background: 'var(--color-bg)',
            border: '1px solid var(--color-border)',
            fontFamily: 'var(--font-mono)',
            color: 'var(--color-text)',
          }}
        >
{`docker exec -it esg_postgres psql -U postgres -d esg_catalyst \\
  -c "UPDATE users SET role='admin' WHERE email='your@email.com';"`}
        </pre>
        <p className="text-xs text-text-subtle mt-3">
          After running this, log out and back in — the new role is read from the JWT on next login.
          To promote to consultant instead, use <code className="px-1 py-0.5 rounded" style={{ background: 'var(--color-surface-raised)', fontFamily: 'var(--font-mono)' }}>role='consultant'</code>.
        </p>
      </div>
    </div>
  )
}