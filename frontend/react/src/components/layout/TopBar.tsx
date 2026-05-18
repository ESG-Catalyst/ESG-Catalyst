import { Bell, Globe } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useUIStore } from '@/store/ui'
import { useLocation } from 'react-router-dom'

const BREADCRUMB_LABELS: Record<string, string> = {
  dashboard: 'Dashboard',
  upload: 'Upload',
  pipeline: 'Pipeline',
  results: 'Results',
  report: 'Report',
  consultant: 'Consultant',
  admin: 'Admin',
}

function useBreadcrumb() {
  const { pathname } = useLocation()
  const segments = pathname.split('/').filter(Boolean)
  return segments.map((seg) => BREADCRUMB_LABELS[seg] ?? seg)
}

export default function TopBar() {
  const { i18n } = useTranslation()
  const { language, setLanguage } = useUIStore()
  const crumbs = useBreadcrumb()

  function toggleLanguage() {
    const next = language === 'en' ? 'ar' : 'en'
    setLanguage(next)
    i18n.changeLanguage(next)
    document.documentElement.lang = next
    document.documentElement.dir = next === 'ar' ? 'rtl' : 'ltr'
    if (next === 'ar') {
      document.body.style.fontFamily = 'var(--font-arabic)'
    } else {
      document.body.style.fontFamily = ''
    }
  }

  return (
    <header className="h-14 flex items-center justify-between px-6 border-b border-border bg-surface shrink-0">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-1 text-sm text-text-muted">
        {crumbs.map((crumb, i) => (
          <span key={i} className="flex items-center gap-1">
            {i > 0 && <span className="text-text-subtle">/</span>}
            <span className={i === crumbs.length - 1 ? 'text-text' : ''}>{crumb}</span>
          </span>
        ))}
      </nav>

      {/* Actions */}
      <div className="flex items-center gap-2">
        {/* Language toggle */}
        <button
          onClick={toggleLanguage}
          className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-text-muted hover:text-text hover:bg-surface-raised rounded transition-colors"
          title="Switch language"
        >
          <Globe size={14} />
          <span className="font-medium">{language.toUpperCase()}</span>
        </button>

        {/* Notifications */}
        <button
          className="relative p-2 text-text-muted hover:text-text hover:bg-surface-raised rounded transition-colors"
          aria-label="Notifications"
        >
          <Bell size={16} />
          <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-primary rounded-full" />
        </button>

        {/* Avatar */}
        <div className="w-7 h-7 rounded-full bg-primary/20 text-primary flex items-center justify-center text-xs font-semibold select-none">
          U
        </div>
      </div>
    </header>
  )
}
