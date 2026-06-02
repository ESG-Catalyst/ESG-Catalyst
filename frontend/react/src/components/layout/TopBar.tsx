import { Bell, Menu } from 'lucide-react'
import { useLocation } from 'react-router-dom'
import { useUIStore } from '@/store/ui'
import { useAuthStore, emailInitials } from '@/store/auth'
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
      // Filter out UUIDs / numeric IDs so breadcrumb stays clean
      return !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(seg) &&
        !/^\d+$/.test(seg)
    })
    .map((seg) => BREADCRUMB_LABELS[seg] ?? seg.charAt(0).toUpperCase() + seg.slice(1))
}

// ─── TopBar ──────────────────────────────────────────────────────────────────

export default function TopBar() {
  const { setMobileSidebarOpen } = useUIStore()
  const { email } = useAuthStore()
  const crumbs = useBreadcrumbs()
  const initials = emailInitials(email)

  return (
    <header
      className={cn(
        'h-14 flex items-center justify-between px-4 md:px-6 shrink-0',
        'sticky top-0 z-30',
        'border-b border-border',
        // Subtle backdrop blur so content scrolling under looks good
        'bg-surface/90 backdrop-blur-sm',
      )}
    >
      {/* Left: mobile hamburger + breadcrumb */}
      <div className="flex items-center gap-3 min-w-0">
        {/* Mobile-only hamburger */}
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

        {/* Breadcrumb */}
        <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-sm text-text-muted min-w-0 overflow-hidden">
          {crumbs.map((crumb, i) => (
            <span key={`${crumb}-${i}`} className="flex items-center gap-1 shrink-0">
              {i > 0 && (
                <span className="text-text-subtle select-none mx-0.5" aria-hidden="true">/</span>
              )}
              <span
                className={cn(
                  'truncate',
                  i === crumbs.length - 1 ? 'text-text font-medium' : 'text-text-muted',
                )}
                aria-current={i === crumbs.length - 1 ? 'page' : undefined}
              >
                {crumb}
              </span>
            </span>
          ))}
        </nav>
      </div>

      {/* Right: notifications + avatar */}
      <div className="flex items-center gap-1.5 shrink-0">
        {/* Notification bell */}
        <button
          className={cn(
            'relative p-2 rounded text-text-muted hover:text-text hover:bg-surface-raised transition-colors',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
          )}
          aria-label="Notifications"
        >
          <Bell size={16} aria-hidden="true" />
          {/* Unread dot */}
          <span
            className="absolute top-1.5 end-1.5 w-1.5 h-1.5 rounded-full bg-primary pointer-events-none"
            aria-hidden="true"
          />
        </button>

        {/* User avatar — shows email-derived initials */}
        <div
          className={cn(
            'w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold select-none',
            'bg-primary/15 text-primary ring-1 ring-primary/30',
          )}
          title={email ?? 'User'}
          aria-label={`Account: ${email ?? 'User'}`}
        >
          {initials}
        </div>
      </div>
    </header>
  )
}
