import { cn } from '@/lib/utils'

export type StatusValue =
  | 'DRAFT' | 'IN_REVIEW' | 'APPROVED' | 'LOCKED'
  | 'extracted' | 'ambiguous' | 'missing' | 'rejected' | 'approved'

interface StatusPillProps {
  status: StatusValue
  /** Render a small dot indicator instead of the full pill */
  dot?: boolean
  className?: string
}

/* ── visual recipe per status ────────────────────────────────────────────── */
const STATUS_STYLES: Record<string, string> = {
  DRAFT:     'bg-surface-raised text-text-muted border-border',
  IN_REVIEW: 'bg-warning-subtle text-warning border-warning/25',
  APPROVED:  'bg-success-subtle text-success border-success/25',
  LOCKED:    'bg-info-subtle   text-info    border-info/25',
  extracted: 'bg-info-subtle   text-info    border-info/25',
  ambiguous: 'bg-warning-subtle text-warning border-warning/25',
  missing:   'bg-surface-raised text-text-muted border-border',
  rejected:  'bg-danger-subtle  text-danger  border-danger/25',
  approved:  'bg-success-subtle text-success border-success/25',
}

/* Dot accent colour only */
const STATUS_DOT: Record<string, string> = {
  DRAFT:     'bg-text-subtle',
  IN_REVIEW: 'bg-warning',
  APPROVED:  'bg-success',
  LOCKED:    'bg-info',
  extracted: 'bg-info',
  ambiguous: 'bg-warning',
  missing:   'bg-text-subtle',
  rejected:  'bg-danger',
  approved:  'bg-success',
}

const STATUS_LABELS: Record<string, string> = {
  DRAFT:     'Draft',
  IN_REVIEW: 'In Review',
  APPROVED:  'Approved',
  LOCKED:    'Locked',
  extracted: 'Extracted',
  ambiguous: 'Ambiguous',
  missing:   'Missing',
  rejected:  'Rejected',
  approved:  'Approved',
}

export default function StatusPill({ status, dot = false, className }: StatusPillProps) {
  const style = STATUS_STYLES[status] ?? 'bg-surface-raised text-text-muted border-border'
  const label = STATUS_LABELS[status] ?? (status.charAt(0).toUpperCase() + status.slice(1).toLowerCase())
  const dotColor = STATUS_DOT[status] ?? 'bg-text-subtle'

  if (dot) {
    return (
      <span
        className={cn('inline-flex items-center gap-1.5', className)}
        title={label}
      >
        <span className={cn('w-2 h-2 rounded-full shrink-0', dotColor)} aria-hidden="true" />
        <span className="text-xs text-text-muted">{label}</span>
      </span>
    )
  }

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full',
        'text-xs font-medium border leading-none select-none',
        'transition-colors duration-fast',
        style,
        className,
      )}
      role="status"
    >
      <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', dotColor)} aria-hidden="true" />
      {label}
    </span>
  )
}
