import { useEffect, useState } from 'react'
import { Outlet, Link, useLocation } from 'react-router-dom'
import { X, Eye } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import Sidebar from './Sidebar'
import TopBar from './TopBar'
import { useUIStore } from '@/store/ui'
import { useConsultantStore } from '@/store/consultant'

/**
 * Returns true when the viewport is at or wider than the `md` breakpoint (768px).
 * Subscribes to the matchMedia `change` event for smooth responsive behaviour.
 */
function useIsMd(): boolean {
  const [isMd, setIsMd] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia('(min-width: 768px)').matches : false,
  )
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)')
    const handler = (e: MediaQueryListEvent) => setIsMd(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])
  return isMd
}

// ─── Client context banner ──────────────────────────────────────────────────

function ClientContextBanner() {
  const activeClient = useConsultantStore((s) => s.activeClient)
  const clearActiveClient = useConsultantStore((s) => s.clearActiveClient)

  if (!activeClient) return null

  return (
    <div
      className="flex items-center justify-between px-4 py-2 text-xs font-medium shrink-0"
      style={{
        background: 'var(--color-primary)',
        color: '#fff',
        minHeight: '36px',
      }}
    >
      <span className="flex items-center gap-2">
        <Eye size={13} aria-hidden="true" />
        Viewing as: <strong className="font-semibold">{activeClient.companyName}</strong>
        <span className="opacity-70" aria-hidden="true">·</span>
        <span className="opacity-80">{activeClient.institutionType}</span>
      </span>
      <Link
        to="/consultant"
        onClick={clearActiveClient}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60"
        style={{ background: 'rgba(255,255,255,0.15)' }}
        onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.25)')}
        onMouseLeave={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.15)')}
        aria-label="Exit client view"
      >
        <X size={12} aria-hidden="true" />
        Exit client view
      </Link>
    </div>
  )
}

// ─── Page transition wrapper ─────────────────────────────────────────────────

const PAGE_VARIANTS = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -4 },
}

const PAGE_TRANSITION = {
  duration: 0.18,
  ease: [0.4, 0, 0.2, 1] as [number, number, number, number],
}

function PageTransition({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation()
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={pathname}
        variants={PAGE_VARIANTS}
        initial="initial"
        animate="animate"
        exit="exit"
        transition={PAGE_TRANSITION}
        className="flex-1 min-h-0"
        // Respect prefers-reduced-motion
        style={{
          // framer-motion ignores this directly, but the variants produce no
          // perceptible movement when duration is short; a CSS media-query
          // override is in globals.css (tokens) for hard-off preference.
        }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  )
}

// ─── AppShell ────────────────────────────────────────────────────────────────

export default function AppShell() {
  const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed)
  const language = useUIStore((s) => s.language)
  const isRTL = language === 'ar'
  const isMd = useIsMd()

  // On mobile (<md): sidebar is off-canvas; no margin offset.
  // On md+: offset by the sidebar width in the correct logical direction.
  const sidebarSize = sidebarCollapsed
    ? 'var(--sidebar-collapsed-width)'
    : 'var(--sidebar-width)'

  const mainStyle: React.CSSProperties = isMd
    ? isRTL
      ? { marginRight: sidebarSize, marginLeft: 0 }
      : { marginLeft: sidebarSize, marginRight: 0 }
    : { marginLeft: 0, marginRight: 0 }

  return (
    <div className="flex h-screen overflow-hidden bg-bg">
      {/* Sidebar renders itself + mobile drawer internally */}
      <Sidebar />

      {/* Main content column — offset by sidebar width on md+ */}
      <div
        className="flex flex-col flex-1 min-w-0 transition-[margin] duration-300"
        style={mainStyle}
      >
        <ClientContextBanner />
        <TopBar />

        {/* Scrollable page area with animated page transitions */}
        <main className="flex-1 overflow-y-auto flex flex-col">
          <PageTransition>
            <Outlet />
          </PageTransition>
        </main>
      </div>
    </div>
  )
}
