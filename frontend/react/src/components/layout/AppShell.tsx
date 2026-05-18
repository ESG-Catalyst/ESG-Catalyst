import { Outlet, Link } from 'react-router-dom'
import { X, Eye } from 'lucide-react'
import Sidebar from './Sidebar'
import TopBar from './TopBar'
import { useUIStore } from '@/store/ui'
import { useConsultantStore } from '@/store/consultant'

function ClientContextBanner() {
  const activeClient = useConsultantStore((s) => s.activeClient)
  const clearActiveClient = useConsultantStore((s) => s.clearActiveClient)

  if (!activeClient) return null

  return (
    <div
      className="flex items-center justify-between px-4 py-2 text-xs font-medium"
      style={{
        background: 'var(--color-primary)',
        color: '#fff',
        minHeight: '36px',
      }}
    >
      <span className="flex items-center gap-2">
        <Eye size={13} />
        Viewing as: <strong className="font-semibold">{activeClient.companyName}</strong>
        <span className="opacity-70">·</span>
        <span className="opacity-80">{activeClient.institutionType}</span>
      </span>
      <Link
        to="/consultant"
        onClick={clearActiveClient}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded transition-colors"
        style={{ background: 'rgba(255,255,255,0.15)' }}
        onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.25)')}
        onMouseLeave={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.15)')}
      >
        <X size={12} />
        Exit client view
      </Link>
    </div>
  )
}

export default function AppShell() {
  const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed)
  const language = useUIStore((s) => s.language)
  const isRTL = language === 'ar'
  const sidebarSize = sidebarCollapsed
    ? 'var(--sidebar-collapsed-width)'
    : 'var(--sidebar-width)'

  return (
    <div className="flex h-screen overflow-hidden bg-bg">
      <Sidebar />
      <div
        className="flex flex-col flex-1 min-w-0 transition-all"
        style={{
          marginLeft: isRTL ? 0 : sidebarSize,
          marginRight: isRTL ? sidebarSize : 0,
        }}
      >
        <ClientContextBanner />
        <TopBar />
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
