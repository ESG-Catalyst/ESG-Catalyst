import { NavLink, Link, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  Upload,
  BarChart2,
  FileText,
  Briefcase,
  Settings,
  ChevronLeft,
  ChevronRight,
  LogOut,
  Globe,
  Sun,
  Moon,
} from 'lucide-react'
import { useUIStore } from '@/store/ui'
import { useAuthStore, emailInitials, emailHandle } from '@/store/auth'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

const MAIN_NAV = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'nav.dashboard' },
  { to: '/upload', icon: Upload, label: 'nav.upload' },
  { to: '/results', icon: BarChart2, label: 'nav.results' },
  { to: '/report', icon: FileText, label: 'Disclosures' },
] as const

// Consultant and Admin are role-gated — shown only when the user has the right role
const TOOLS_NAV = [
  { to: '/consultant', icon: Briefcase, label: 'nav.consultant', roles: ['consultant', 'admin'] },
  { to: '/admin', icon: Settings, label: 'nav.admin', roles: ['admin'] },
] as const

export default function Sidebar() {
  const { i18n, t } = useTranslation()
  const navigate = useNavigate()
  const { sidebarCollapsed, toggleSidebar, language, setLanguage, theme, toggleTheme } = useUIStore()
  const { email, role, clearAuth } = useAuthStore()
  const isRTL = language === 'ar'

  function handleLogout() {
    clearAuth()
    navigate('/auth/login')
  }

  function toggleLang() {
    const next = language === 'en' ? 'ar' : 'en'
    setLanguage(next)
    i18n.changeLanguage(next)
    document.documentElement.lang = next
    document.documentElement.dir = next === 'ar' ? 'rtl' : 'ltr'
  }

  function NavItem({
    to,
    label,
    icon: Icon,
  }: {
    to: string
    icon: React.ElementType
    label: string
  }) {
    // Translate if it's an i18n key (contains dot), otherwise use as-is
    const displayLabel = label.includes('.') ? t(label) : label
    return (
      <NavLink
        to={to}
        className={({ isActive }) =>
          cn(
            'flex items-center gap-3 px-4 py-2.5 text-sm transition-colors hover:bg-surface-raised relative',
            isActive ? 'text-primary bg-surface-raised' : 'text-text-muted hover:text-text',
          )
        }
      >
        {({ isActive }) => (
          <>
            {isActive && (
              <span
                className="absolute top-1 bottom-1 w-0.5 rounded"
                style={{
                  background: 'var(--color-primary)',
                  [isRTL ? 'right' : 'left']: 0,
                }}
              />
            )}
            <Icon size={18} className="shrink-0" />
            {!sidebarCollapsed && (
              <span className="whitespace-nowrap">{displayLabel}</span>
            )}
          </>
        )}
      </NavLink>
    )
  }

  const sideEdge = isRTL ? 'right-0' : 'left-0'

  // Visible tool nav items filtered by role
  const visibleTools = TOOLS_NAV.filter((item) =>
    (item.roles as readonly string[]).includes(role),
  )

  const initials = emailInitials(email)
  const handle = emailHandle(email)

  return (
    <aside
      className={`fixed top-0 ${sideEdge} h-full flex flex-col z-40 transition-all duration-300`}
      style={{
        width: sidebarCollapsed ? 'var(--sidebar-collapsed-width)' : 'var(--sidebar-width)',
        background: 'var(--color-surface)',
        [isRTL ? 'borderLeft' : 'borderRight']: '1px solid var(--color-border)',
      }}
    >
      {/* Wordmark — clicking goes to Landing page */}
      <div
        className="flex items-center px-4 h-14 shrink-0 overflow-hidden"
        style={{ borderBottom: '1px solid var(--color-border)' }}
      >
        <Link
          to="/"
          className="flex items-center gap-1 hover:opacity-80 transition-opacity"
          title="Home"
        >
          {sidebarCollapsed ? (
            <span className="text-base font-bold" style={{ color: 'var(--color-primary)' }}>E</span>
          ) : (
            <span className="text-sm font-semibold whitespace-nowrap">
              <span style={{ color: 'var(--color-primary)' }}>ESG</span>
              <span className="text-text"> Catalyst</span>
            </span>
          )}
        </Link>
      </div>

      {/* Main nav */}
      <nav className="flex-1 py-2 overflow-y-auto overflow-x-hidden">
        <div className="flex flex-col">
          {MAIN_NAV.map((item) => (
            <NavItem key={item.to} {...item} />
          ))}
        </div>

        {/* Tools section — only shown if the user's role allows it */}
        {visibleTools.length > 0 && (
          <>
            <div className="my-2 mx-4 border-t" style={{ borderColor: 'var(--color-border)' }} />
            {!sidebarCollapsed && (
              <p className="px-4 pb-1 text-xs font-semibold uppercase tracking-widest text-text-subtle">
                Tools
              </p>
            )}
            <div className="flex flex-col">
              {visibleTools.map((item) => (
                <NavItem key={item.to} {...item} />
              ))}
            </div>
          </>
        )}
      </nav>

      {/* Bottom area */}
      <div style={{ borderTop: '1px solid var(--color-border)' }}>
        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          className="flex items-center gap-3 px-4 py-2.5 w-full text-sm text-text-muted hover:text-text hover:bg-surface-raised transition-colors"
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {theme === 'dark'
            ? <Sun size={18} className="shrink-0" />
            : <Moon size={18} className="shrink-0" />}
          {!sidebarCollapsed && (
            <span className="whitespace-nowrap">{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
          )}
        </button>

        {/* Language toggle */}
        <button
          onClick={toggleLang}
          className="flex items-center gap-3 px-4 py-2.5 w-full text-sm text-text-muted hover:text-text hover:bg-surface-raised transition-colors"
        >
          <Globe size={18} className="shrink-0" />
          {!sidebarCollapsed && (
            <span className="whitespace-nowrap">{language === 'en' ? 'العربية' : 'English'}</span>
          )}
        </button>

        {/* User row — shows email-derived initials + handle, hides raw UUID */}
        <div className="flex items-center gap-2.5 px-4 py-2.5">
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 select-none"
            style={{ background: 'var(--color-primary)', color: '#fff' }}
            title={email ?? 'User'}
          >
            {initials}
          </div>
          {!sidebarCollapsed && (
            <div className="flex flex-col min-w-0">
              <span className="text-xs font-medium text-text truncate">{handle}</span>
              <span
                className="text-xs text-text-subtle truncate"
                style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem' }}
              >
                {role}
              </span>
            </div>
          )}
        </div>

        {/* Logout */}
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-4 py-2.5 w-full text-sm text-text-muted hover:text-danger hover:bg-surface-raised transition-colors"
        >
          <LogOut size={18} className="shrink-0" />
          {!sidebarCollapsed && <span>{t('nav.logout')}</span>}
        </button>

        {/* Collapse toggle */}
        <button
          onClick={toggleSidebar}
          className="flex items-center gap-3 px-4 py-2.5 w-full text-sm text-text-subtle hover:text-text hover:bg-surface-raised transition-colors"
          aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {sidebarCollapsed ? (
            isRTL ? <ChevronLeft size={18} className="shrink-0" /> : <ChevronRight size={18} className="shrink-0" />
          ) : (
            <>
              {isRTL ? <ChevronRight size={18} className="shrink-0" /> : <ChevronLeft size={18} className="shrink-0" />}
              {!sidebarCollapsed && <span>{t('nav.collapse')}</span>}
            </>
          )}
        </button>
      </div>
    </aside>
  )
}