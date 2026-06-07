import { useEffect, useRef, useState } from 'react'
import { Bell, Menu, LogOut, LayoutDashboard, CheckCircle2 } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useUIStore } from '@/store/ui'
import { useAuthStore, emailInitials, emailHandle } from '@/store/auth'
import { cn } from '@/lib/utils'

// ─── Breadcrumb labels ───────────────────────────────────────────────────────

const BREADCRUMB_LABELS: Record<string, string> = {
  dashboard: 'Dashboard',
  upload: 'Upload',
  pipeline: 'Pipeline',
  results: 'Results',
  report: 'Disclosures',
  consultant: 'Consultant',
  admin: 'Admin',
  auth: 'Auth',
  login: 'Login',
  register: 'Register',
}

function useBreadcrumbs() {
  const { pathname } = useLocation()
  const segments = pathname.split('/').filter(Boolean)
  return segments
    .filter((seg) => {
      return !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(seg) &&
        !/^\d+$/.test(seg)
    })
    .map((seg) => BREADCRUMB_LABELS[seg] ?? seg.charAt(0).toUpperCase() + seg.slice(1))
}

// ─── TopBar ──────────────────────────────────────────────────────────────────

export default function TopBar() {
  const { setMobileSidebarOpen } = useUIStore()
  const email = useAuthStore((s) => s.email)
  const clearAuth = useAuthStore((s) => s.clearAuth)
  const navigate = useNavigate()
  const crumbs = useBreadcrumbs()
  const initials = emailInitials(email)

  const [notifOpen, setNotifOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const notifRef = useRef<HTMLDivElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  // Close popovers on outside click or Escape.
  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) setNotifOpen(false)
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setNotifOpen(false)
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [])

  function handleSignOut() {
    setMenuOpen(false)
    clearAuth()
    navigate('/', { replace: true })
  }

  const menuItemCls = cn(
    'w-full flex items-center gap-2.5 px-4 py-2 text-sm text-start transition-colors',
    'text-text-muted hover:text-text hover:bg-surface-raised',
    'focus-visible:outline-none focus-visible:bg-surface-raised',
  )

  return (
    <header
      className={cn(
        'h-14 flex items-center justify-between px-4 md:px-6 shrink-0',
        'sticky top-0 z-30',
        'border-b border-border',
        'bg-surface/90 backdrop-blur-sm',
      )}
    >
      {/* Left: mobile hamburger + breadcrumb */}
      <div className="flex items-center gap-3 min-w-0">
        <button
          className={cn(
            'md:hidden p-2 -ms-1 rounded text-text-muted hover:text-text hover:bg-surface-raised transition-colors',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
          )}
          aria-label="Open navigation menu"
          onClick={() => setMobileSidebarOpen(true)}
        >
          <Menu size={18} aria-hidden="true" />
        </button>

        <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-sm text-text-muted min-w-0 overflow-hidden">
          {crumbs.map((crumb, i) => (
            <span key={`${crumb}-${i}`} className="flex items-center gap-1 shrink-0">
              {i > 0 && (
                <span className="text-text-subtle select-none mx-0.5" aria-hidden="true">/</span>
              )}
              <span
                className={cn('truncate', i === crumbs.length - 1 ? 'text-text font-medium' : 'text-text-muted')}
                aria-current={i === crumbs.length - 1 ? 'page' : undefined}
              >
                {crumb}
              </span>
            </span>
          ))}
        </nav>
      </div>

      {/* Right: notifications + avatar menu */}
      <div className="flex items-center gap-1.5 shrink-0">
        {/* Notifications */}
        <div className="relative" ref={notifRef}>
          <button
            type="button"
            onClick={() => { setNotifOpen((o) => !o); setMenuOpen(false) }}
            className={cn(
              'relative p-2 rounded text-text-muted hover:text-text hover:bg-surface-raised transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
              notifOpen && 'text-text bg-surface-raised',
            )}
            aria-label="Notifications"
            aria-haspopup="menu"
            aria-expanded={notifOpen}
          >
            <Bell size={16} aria-hidden="true" />
          </button>

          {notifOpen && (
            <div
              role="menu"
              aria-label="Notifications"
              className="absolute end-0 mt-2 w-72 rounded-lg overflow-hidden z-50"
              style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', boxShadow: '0 12px 32px rgba(0,0,0,0.18)' }}
            >
              <div className="px-4 py-3 border-b border-border text-sm font-semibold text-text">Notifications</div>
              <div className="flex flex-col items-center justify-center gap-2 px-4 py-8 text-center">
                <CheckCircle2 size={22} style={{ color: 'var(--color-primary)' }} aria-hidden="true" />
                <p className="text-sm text-text-muted">You're all caught up</p>
                <p className="text-xs text-text-subtle">Pipeline and review alerts will appear here.</p>
              </div>
            </div>
          )}
        </div>

        {/* Avatar / account menu */}
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => { setMenuOpen((o) => !o); setNotifOpen(false) }}
            className={cn(
              'w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold select-none transition-shadow',
              'bg-primary/15 text-primary ring-1 ring-primary/30',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
              menuOpen && 'ring-2 ring-primary',
            )}
            title={email ?? 'Account'}
            aria-label="Account menu"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
          >
            {initials}
          </button>

          {menuOpen && (
            <div
              role="menu"
              aria-label="Account"
              className="absolute end-0 mt-2 w-56 rounded-lg overflow-hidden z-50"
              style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', boxShadow: '0 12px 32px rgba(0,0,0,0.18)' }}
            >
              <div className="px-4 py-3 border-b border-border">
                <p className="text-sm font-semibold text-text truncate">{emailHandle(email)}</p>
                <p className="text-xs text-text-muted truncate">{email ?? 'Signed in'}</p>
              </div>
              <div className="py-1">
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => { setMenuOpen(false); navigate('/dashboard') }}
                  className={menuItemCls}
                >
                  <LayoutDashboard size={14} aria-hidden="true" />
                  Dashboard
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={handleSignOut}
                  className={cn(menuItemCls, 'text-danger hover:text-danger')}
                >
                  <LogOut size={14} aria-hidden="true" />
                  Sign out
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
