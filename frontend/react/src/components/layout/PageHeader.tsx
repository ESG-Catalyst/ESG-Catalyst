import { type ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface PageHeaderProps {
  title: string
  /**
   * Short subtitle shown below the title (replaces the old `subtitle` prop
   * while keeping it available as an alias).
   */
  description?: string
  /** @deprecated Use `description` instead. Kept for backwards compat. */
  subtitle?: string
  /** Optional slot — renders flush end-aligned on desktop, below title on mobile. */
  action?: ReactNode
  /** Extra classes applied to the outer wrapper. */
  className?: string
}

/**
 * Consistent page title + description + optional action slot.
 * RTL-safe: text aligns to `text-start`, action slot sits at `text-end`.
 */
export default function PageHeader({
  title,
  description,
  subtitle,
  action,
  className,
}: PageHeaderProps) {
  const desc = description ?? subtitle

  return (
    <div
      className={cn(
        'flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-6',
        className,
      )}
    >
      <div className="min-w-0">
        <h1 className="text-xl font-semibold text-text leading-tight text-start">{title}</h1>
        {desc && (
          <p className="mt-1 text-sm text-text-muted text-start leading-relaxed">{desc}</p>
        )}
      </div>
      {action && (
        <div className="shrink-0 flex items-start justify-start sm:justify-end">{action}</div>
      )}
    </div>
  )
}
