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
  Terminal,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import apiClient from '@/api/client'
import { useAuthStore } from '@/store/auth'
import type { UserRole } from '@/store/auth'
import { cn } from '@/lib/utils'

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

// ─── Role metadata ────────────────────────────────────────────────────────────

const ROLE_META: Record<UserRole, { label: string; color: string; bg: string }> = {
  company: { label: 'Company', color: '#38BDF8', bg: 'rgba(56,189,248,0.12)' },
  company_admin: { label: 'Company Admin', color: '#6366F1', bg: 'rgba(99,102,241,0.12)' },
  consultant: { label: 'Consultant', color: '#F59E0B', bg: 'rgba(245,158,11,0.12)' },
  admin: { label: 'Admin', color: '#EF4444', bg: 'rgba(239,68,68,0.12)' },
}

const ALL_ROLES: UserRole[] = ['company', 'company_admin', 'consultant', 'admin']

function timeAgo(iso: string) {
  const d = (Date.now() - new Date(iso).getTime()) / 1000
  if (d < 60) return 'just now'
  if (d < 3600) return `${Math.floor(d / 60)}m ago`
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`
  return `${Math.floor(d / 86400)}d ago`
}

// ─── Role selector dropdown ───────────────────────────────────────────────────

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
        aria-haspopup="listbox"
        aria-expanded={open}
        title={isSelf ? "Can't change your own role" : 'Change role'}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        style={{ background: meta.bg, color: meta.color }}
      >
        {meta.label}
        {!isSelf && (
          <ChevronDown
            size={11}
            className={cn('transition-transform', open && 'rotate-180')}
            aria-hidden="true"
          />
        )}
        {mutation.isPending && (
          <RefreshCw size={11} className="animate-spin ms-0.5" aria-label="Saving…" />
        )}
        {mutation.isSuccess && !mutation.isPending && (
          <Check size={11} className="ms-0.5" aria-label="Saved" />
        )}
      </button>

      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
            <motion.div
              initial={{ opacity: 0, y: -4, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -4, scale: 0.97 }}
              transition={{ duration: 0.12 }}
              className="absolute end-0 top-full mt-1.5 z-20 rounded-xl overflow-hidden py-1 min-w-[170px] shadow-xl bg-surface border border-border"
              role="listbox"
              aria-label="Select role"
            >
              {ALL_ROLES.map((r) => {
                const rm = ROLE_META[r]
                const isActive = r === current
                return (
                  <button
                    key={r}
                    role="option"
                    aria-selected={isActive}
                    onClick={() => {
                      mutation.mutate(r)
                      setOpen(false)
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2.5 text-xs hover:bg-surface-raised transition-colors text-start focus-visible:outline-none focus-visible:bg-surface-raised"
                  >
                    <span
                      className="w-2 h-2 rounded-full shrink-0"
                      style={{ background: rm.color }}
                      aria-hidden="true"
                    />
                    <span
                      className="flex-1"
                      style={{ color: isActive ? rm.color : 'var(--color-text)' }}
                    >
                      {rm.label}
                    </span>
                    {isActive && (
                      <Check size={11} className="ms-auto" style={{ color: rm.color }} aria-hidden="true" />
                    )}
                  </button>
                )
              })}
            </motion.div>
          </>
        )}
      </AnimatePresence>
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
            className="rounded-xl px-4 py-3 flex flex-col gap-1 bg-surface border border-border"
          >
            <span className="text-[10px] font-semibold uppercase tracking-widest text-text-muted">
              {m.label}
            </span>
            <span className="text-2xl font-bold tabular-nums" style={{ color: m.color, fontFamily: 'var(--font-mono)' }}>
              {count}
            </span>
          </div>
        )
      })}
    </div>
  )
}

// ─── Avatar ───────────────────────────────────────────────────────────────────

function UserAvatar({ email, isSelf }: { email: string; isSelf: boolean }) {
  const initials = (() => {
    const local = email.split('@')[0]
    const parts = local.split(/[._\-+]/).filter(Boolean)
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
    return local.slice(0, 2).toUpperCase()
  })()

  return (
    <div
      className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0 text-white"
      style={{ background: isSelf ? 'var(--color-primary)' : 'var(--color-surface-raised)', color: isSelf ? '#fff' : 'var(--color-text-muted)', border: isSelf ? 'none' : '1px solid var(--color-border)' }}
      aria-hidden="true"
    >
      {initials}
    </div>
  )
}

// ─── Table skeleton row ───────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <tr className="border-b border-border" aria-hidden="true">
      {[80, 60, 40, 30, 20].map((w, j) => (
        <td key={j} className="px-4 py-3">
          <div
            className="h-4 rounded animate-pulse bg-surface-raised"
            style={{ width: `${w}%` }}
          />
        </td>
      ))}
    </tr>
  )
}

// ─── Admin page ───────────────────────────────────────────────────────────────

export default function Admin() {
  const selfId = useAuthStore((s) => s.userId)
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState<UserRole | 'all'>('all')

  const { data: users = [], isLoading, error, refetch, isFetching } = useQuery({
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
      {/* Page header */}
      <div className="flex items-start justify-between mb-6 gap-4">
        <div>
          <div className="flex items-center gap-2.5 mb-1">
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center"
              style={{ background: 'rgba(239,68,68,0.12)' }}
            >
              <Shield size={15} style={{ color: '#EF4444' }} aria-hidden="true" />
            </div>
            <h1 className="text-xl font-semibold text-text">Admin Console</h1>
          </div>
          <p className="text-sm text-text-muted">Manage users, roles, and institutions.</p>
        </div>
        <button
          onClick={() => refetch()}
          aria-label="Refresh user list"
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-text-muted',
            'hover:text-text hover:bg-surface-raised border border-border transition-colors',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
          )}
        >
          <RefreshCw size={13} className={isFetching ? 'animate-spin' : ''} aria-hidden="true" />
          Refresh
        </button>
      </div>

      {/* Stats */}
      {!isLoading && !error && <StatsBar users={users} />}
      {isLoading && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-16 rounded-xl animate-pulse bg-surface-raised" />
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        {/* Search */}
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search
            size={14}
            className="absolute start-3 top-1/2 -translate-y-1/2 text-text-muted"
            aria-hidden="true"
          />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search users…"
            aria-label="Search users"
            className="w-full ps-9 pe-4 py-2 text-sm rounded-lg bg-surface border border-border-subtle hover:border-border text-text placeholder:text-text-subtle outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:border-primary transition-colors"
          />
        </div>

        {/* Role filter chips */}
        <div className="flex items-center gap-1.5 flex-wrap" role="group" aria-label="Filter by role">
          {(['all', ...ALL_ROLES] as const).map((r) => {
            const label = r === 'all' ? 'All' : ROLE_META[r].label
            const active = roleFilter === r
            return (
              <button
                key={r}
                onClick={() => setRoleFilter(r)}
                aria-pressed={active}
                className={cn(
                  'px-2.5 py-1 rounded-lg text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
                  active
                    ? 'bg-primary text-white border border-transparent'
                    : 'bg-surface text-text-muted border border-border hover:text-text hover:border-border',
                )}
              >
                {label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Error state */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-start gap-3 px-4 py-4 rounded-xl mb-4"
            style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)' }}
            role="alert"
          >
            <AlertCircle size={16} style={{ color: '#EF4444' }} className="mt-0.5 shrink-0" aria-hidden="true" />
            <div>
              <p className="text-sm font-semibold" style={{ color: '#EF4444' }}>
                Could not load users
              </p>
              <p className="text-xs text-text-muted mt-0.5">
                The admin API endpoint may not be deployed yet. See the instructions below to
                promote your account.
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* User table */}
      {!error && (
        <div className="rounded-xl overflow-hidden border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-raised border-b border-border">
                {['User', 'Institution', 'Role', 'Joined', ''].map((h) => (
                  <th
                    key={h}
                    scope="col"
                    className="px-4 py-3 text-start text-xs font-semibold text-text-muted whitespace-nowrap"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {/* Loading skeletons */}
              {isLoading &&
                Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)}

              {/* Data rows */}
              {!isLoading &&
                filtered.map((u, i) => {
                  const isSelf = u.id === selfId
                  return (
                    <tr
                      key={u.id}
                      className={cn(
                        'border-b border-border transition-colors hover:bg-surface-raised/40',
                        i % 2 === 0 ? 'bg-surface' : 'bg-bg',
                        isSelf && 'ring-1 ring-inset ring-primary/20',
                      )}
                    >
                      {/* User */}
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2.5">
                          <UserAvatar email={u.email} isSelf={isSelf} />
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-text truncate">
                              {u.full_name || u.email.split('@')[0]}
                            </p>
                            <p className="text-xs text-text-muted truncate">{u.email}</p>
                          </div>
                        </div>
                      </td>

                      {/* Institution */}
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5">
                          <Building2 size={12} className="text-text-subtle shrink-0" aria-hidden="true" />
                          <span className="text-xs text-text truncate max-w-[160px]">
                            {u.institution_name || '—'}
                          </span>
                        </div>
                        {u.institution_type && (
                          <p className="text-xs text-text-subtle mt-0.5 ms-4.5">
                            {u.institution_type.replace(/_/g, ' ')}
                          </p>
                        )}
                      </td>

                      {/* Role */}
                      <td className="px-4 py-3">
                        <RoleSelector userId={u.id} current={u.role} selfId={selfId} />
                      </td>

                      {/* Joined */}
                      <td className="px-4 py-3 text-xs text-text-muted whitespace-nowrap">
                        {timeAgo(u.created_at)}
                      </td>

                      {/* You badge */}
                      <td className="px-4 py-3">
                        {isSelf && (
                          <span className="text-xs text-text-subtle italic px-2 py-0.5 rounded-full bg-surface-raised border border-border">
                            you
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })}

              {/* Empty state */}
              {!isLoading && filtered.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center">
                    <Users size={22} className="mx-auto mb-2 opacity-30 text-text-subtle" aria-hidden="true" />
                    <p className="text-sm text-text-subtle">No users match the current filter.</p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* User count footer */}
      {!isLoading && !error && filtered.length > 0 && (
        <p className="mt-2 text-xs text-text-subtle text-end">
          Showing {filtered.length} of {users.length} user{users.length !== 1 ? 's' : ''}
        </p>
      )}

      {/* Admin access instructions */}
      <div className="mt-8 rounded-xl p-5 bg-surface border border-border">
        <div className="flex items-center gap-2.5 mb-3">
          <Terminal size={14} style={{ color: 'var(--color-primary)' }} aria-hidden="true" />
          <p className="text-sm font-semibold text-text">How to grant admin access</p>
        </div>
        <p className="text-xs text-text-muted mb-3">
          Run the command below in a terminal to promote any registered user to admin:
        </p>
        <pre
          className="text-xs rounded-lg px-4 py-3 overflow-x-auto bg-bg border border-border"
          style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-text)' }}
        >
{`docker exec -it esg_postgres psql -U postgres -d esg_catalyst \\
  -c "UPDATE users SET role='admin' WHERE email='your@email.com';"`}
        </pre>
        <p className="text-xs text-text-subtle mt-3 leading-relaxed">
          After running this, log out and back in — the new role is read from the JWT on next
          login. To promote to consultant instead, replace{' '}
          <code
            className="px-1.5 py-0.5 rounded"
            style={{ background: 'var(--color-surface-raised)', fontFamily: 'var(--font-mono)' }}
          >
            admin
          </code>{' '}
          with{' '}
          <code
            className="px-1.5 py-0.5 rounded"
            style={{ background: 'var(--color-surface-raised)', fontFamily: 'var(--font-mono)' }}
          >
            consultant
          </code>
          .
        </p>
      </div>
    </div>
  )
}
