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
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { useUIStore, applyLang } from '@/store/ui'
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

// ─── Sidebar inner (shared between full and collapsed) ──────────────────────

function SidebarInner({ onNavClick }: { onNavClick?: () => void }) {
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
    const next: 'en' | 'ar' = language === 'en' ? 'ar' : 'en'
    setLanguage(next)
    i18n.changeLanguage(next)
    applyLang(next)
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
    const displayLabel = label.includes('.') ? t(label) : label
    return (
      <NavLink
        to={to}
        end
        onClick={onNavClick}
        aria-label={displayLabel}
        className={({ isActive }) =>
          cn(
            'relative flex items-center gap-3 px-3 py-2.5 text-sm rounded-md mx-1.5 transition-colors duration-150',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
            isActive
              ? 'text-primary bg-primary/10 font-medium'
              : 'text-text-muted hover:text-text hover:bg-surface-raised',
          )
        }
      >
        {({ isActive }) => (
          <>
            {/* Active indicator bar — on the inner edge in RTL, outer edge in LTR */}
            {isActive && (
              <span
                className="absolute top-1 bottom-1 w-0.5 rounded-full"
                style={{
                  background: 'var(--color-primary)',
                  [isRTL ? 'insetInlineEnd' : 'insetInlineStart']: 0,
                }}
                aria-hidden="true"
              />
            )}
            <Icon size={17} className="shrink-0" aria-hidden="true" />
            <AnimatePresence initial={false}>
              {!sidebarCollapsed && (
                <motion.span
                  key="label"
                  initial={{ opacity: 0, width: 0 }}
                  animate={{ opacity: 1, width: 'auto' }}
                  exit={{ opacity: 0, width: 0 }}
                  transition={{ duration: 0.18 }}
                  className="whitespace-nowrap overflow-hidden"
                >
                  {displayLabel}
                </motion.span>
              )}
            </AnimatePresence>
          </>
        )}
      </NavLink>
    )
  }

  // Visible tool nav items filtered by role
  const visibleTools = TOOLS_NAV.filter((item) =>
    (item.roles as readonly string[]).includes(role),
  )

  const initials = emailInitials(email)
  const handle = emailHandle(email)

  // Collapse icon logic:
  // LTR: collapsed=PanelLeftOpen (expand), expanded=PanelLeftClose (collapse)
  // RTL: collapsed=ChevronLeft  (expand toward left), expanded=ChevronRight (collapse toward right)
  const CollapseIcon = sidebarCollapsed
    ? isRTL ? ChevronLeft : PanelLeftOpen
    : isRTL ? ChevronRight : PanelLeftClose

  return (
    <div className="flex flex-col h-full">
      {/* Wordmark */}
      <div
        className="flex items-center h-14 px-4 shrink-0"
        style={{ borderBottom: '1px solid var(--color-border)' }}
      >
        <Link
          to="/"
          className="flex items-center gap-1.5 hover:opacity-80 transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded"
          title="ESG Catalyst Home"
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
      <nav aria-label="Main navigation" className="flex-1 py-2 overflow-y-auto overflow-x-hidden">
        <ul className="flex flex-col gap-0.5" role="list">
          {MAIN_NAV.map((item) => (
            <li key={item.to}>
              <NavItem {...item} />
            </li>
          ))}
        </ul>

        {/* Tools section — role-gated */}
        {visibleTools.length > 0 && (
          <div className="mt-2">
            <div className="mx-4 my-1.5 border-t" style={{ borderColor: 'var(--color-border)' }} />
            <AnimatePresence initial={false}>
              {!sidebarCollapsed && (
                <motion.p
                  key="tools-label"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="px-4 pb-1 pt-0.5 text-xs font-semibold uppercase tracking-widest text-text-subtle"
                >
                  Tools
                </motion.p>
              )}
            </AnimatePresence>
            <ul className="flex flex-col gap-0.5" role="list">
              {visibleTools.map((item) => (
                <li key={item.to}>
                  <NavItem {...item} />
                </li>
              ))}
            </ul>
          </div>
        )}
      </nav>

      {/* Bottom controls */}
      <div className="shrink-0" style={{ borderTop: '1px solid var(--color-border)' }}>
        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          className={cn(
            'flex items-center gap-3 w-full px-4 py-2.5 text-sm text-text-muted',
            'hover:text-text hover:bg-surface-raised transition-colors',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
          )}
        >
          {theme === 'dark'
            ? <Sun size={17} className="shrink-0" aria-hidden="true" />
            : <Moon size={17} className="shrink-0" aria-hidden="true" />}
          <AnimatePresence initial={false}>
            {!sidebarCollapsed && (
              <motion.span
                key="theme-label"
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: 'auto' }}
                exit={{ opacity: 0, width: 0 }}
                transition={{ duration: 0.15 }}
                className="whitespace-nowrap overflow-hidden"
              >
                {theme === 'dark' ? 'Light mode' : 'Dark mode'}
              </motion.span>
            )}
          </AnimatePresence>
        </button>

        {/* Language toggle */}
        <button
          onClick={toggleLang}
          aria-label={language === 'en' ? 'Switch to Arabic' : 'Switch to English'}
          className={cn(
            'flex items-center gap-3 w-full px-4 py-2.5 text-sm text-text-muted',
            'hover:text-text hover:bg-surface-raised transition-colors',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
          )}
        >
          <Globe size={17} className="shrink-0" aria-hidden="true" />
          <AnimatePresence initial={false}>
            {!sidebarCollapsed && (
              <motion.span
                key="lang-label"
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: 'auto' }}
                exit={{ opacity: 0, width: 0 }}
                transition={{ duration: 0.15 }}
                className="whitespace-nowrap overflow-hidden"
              >
                {language === 'en' ? 'العربية' : 'English'}
              </motion.span>
            )}
          </AnimatePresence>
        </button>

        {/* User identity row */}
        <div className="flex items-center gap-2.5 px-4 py-2.5">
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 select-none"
            style={{ background: 'var(--color-primary)', color: '#fff' }}
            title={email ?? 'User'}
            aria-label={`Logged in as ${email ?? 'User'}`}
          >
            {initials}
          </div>
          <AnimatePresence initial={false}>
            {!sidebarCollapsed && (
              <motion.div
                key="user-meta"
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: 'auto' }}
                exit={{ opacity: 0, width: 0 }}
                transition={{ duration: 0.15 }}
                className="flex flex-col min-w-0 overflow-hidden"
              >
                <span className="text-xs font-medium text-text truncate">{handle}</span>
                <span
                  className="text-xs text-text-subtle truncate"
                  style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem' }}
                >
                  {role}
                </span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Logout */}
        <button
          onClick={handleLogout}
          aria-label="Log out"
          className={cn(
            'flex items-center gap-3 w-full px-4 py-2.5 text-sm text-text-muted',
            'hover:text-danger hover:bg-surface-raised transition-colors',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
          )}
        >
          <LogOut size={17} className="shrink-0" aria-hidden="true" />
          <AnimatePresence initial={false}>
            {!sidebarCollapsed && (
              <motion.span
                key="logout-label"
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: 'auto' }}
                exit={{ opacity: 0, width: 0 }}
                transition={{ duration: 0.15 }}
                className="whitespace-nowrap overflow-hidden"
              >
                {t('nav.logout')}
              </motion.span>
            )}
          </AnimatePresence>
        </button>

        {/* Collapse toggle */}
        <button
          onClick={toggleSidebar}
          aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className={cn(
            'flex items-center gap-3 w-full px-4 py-2.5 text-sm text-text-subtle',
            'hover:text-text hover:bg-surface-raised transition-colors',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
          )}
        >
          <CollapseIcon size={17} className="shrink-0" aria-hidden="true" />
          <AnimatePresence initial={false}>
            {!sidebarCollapsed && (
              <motion.span
                key="collapse-label"
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: 'auto' }}
                exit={{ opacity: 0, width: 0 }}
                transition={{ duration: 0.15 }}
                className="whitespace-nowrap overflow-hidden"
              >
                {t('nav.collapse')}
              </motion.span>
            )}
          </AnimatePresence>
        </button>
      </div>
    </div>
  )
}

// ─── Main Sidebar export ────────────────────────────────────────────────────

export default function Sidebar() {
  const { sidebarCollapsed, language, mobileSidebarOpen, setMobileSidebarOpen } = useUIStore()
  const isRTL = language === 'ar'

  const sideEdge = isRTL ? 'end-0' : 'start-0'
  const sideWidth = sidebarCollapsed ? 'var(--sidebar-collapsed-width)' : 'var(--sidebar-width)'

  return (
    <>
      {/* ── Desktop sidebar (hidden on mobile) ─────────────────────────────── */}
      <motion.aside
        role="complementary"
        aria-label="Application sidebar"
        animate={{ width: sidebarCollapsed ? 'var(--sidebar-collapsed-width)' : 'var(--sidebar-width)' }}
        transition={{ type: 'spring', stiffness: 320, damping: 36, mass: 0.8 }}
        className={`hidden md:flex flex-col fixed top-0 ${sideEdge} h-full z-40 overflow-hidden`}
        style={{
          background: 'var(--color-surface)',
          [isRTL ? 'borderLeft' : 'borderRight']: '1px solid var(--color-border)',
        }}
      >
        <SidebarInner />
      </motion.aside>

      {/* ── Mobile: overlay + drawer ────────────────────────────────────────── */}
      <AnimatePresence>
        {mobileSidebarOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              key="sidebar-backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="fixed inset-0 z-40 bg-black/60 md:hidden"
              aria-hidden="true"
              onClick={() => setMobileSidebarOpen(false)}
            />
            {/* Drawer */}
            <motion.aside
              key="sidebar-drawer"
              role="dialog"
              aria-modal="true"
              aria-label="Navigation menu"
              initial={{ x: isRTL ? '100%' : '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: isRTL ? '100%' : '-100%' }}
              transition={{ type: 'spring', stiffness: 320, damping: 36, mass: 0.8 }}
              className={`fixed top-0 ${sideEdge} h-full z-50 md:hidden flex flex-col overflow-hidden`}
              style={{
                width: sideWidth,
                background: 'var(--color-surface)',
                [isRTL ? 'borderLeft' : 'borderRight']: '1px solid var(--color-border)',
              }}
            >
              <SidebarInner onNavClick={() => setMobileSidebarOpen(false)} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  )
}
