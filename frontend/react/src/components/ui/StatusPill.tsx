import { cn } from '@/lib/utils'

export type StatusValue = 'DRAFT' | 'IN_REVIEW' | 'APPROVED' | 'LOCKED'
  | 'extracted' | 'ambiguous' | 'missing' | 'rejected' | 'approved'

interface StatusPillProps {
  status: StatusValue
  className?: string
}

const STATUS_STYLES: Record<string, string> = {
  DRAFT: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
  IN_REVIEW: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  APPROVED: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  LOCKED: 'bg-violet-500/15 text-violet-400 border-violet-500/30',
  extracted: 'bg-sky-500/15 text-sky-400 border-sky-500/30',
  ambiguous: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  missing: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
  rejected: 'bg-red-500/15 text-red-400 border-red-500/30',
  approved: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
}

const STATUS_LABELS: Record<string, string> = {
  IN_REVIEW: 'In Review',
  extracted: 'Extracted',
  ambiguous: 'Ambiguous',
  missing: 'Missing',
  rejected: 'Rejected',
  approved: 'Approved',
}

export default function StatusPill({ status, className }: StatusPillProps) {
  const style = STATUS_STYLES[status] ?? 'bg-slate-500/15 text-slate-400 border-slate-500/30'
  const label = STATUS_LABELS[status] ?? status.charAt(0).toUpperCase() + status.slice(1).toLowerCase()

  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border',
        style,
        className,
      )}
    >
      {label}
    </span>
  )
}
