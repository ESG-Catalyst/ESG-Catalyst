import { Sparkles, Check, Pencil, X } from 'lucide-react'
import { cn } from '@/lib/utils'

interface AIProposalBannerProps {
  message?: string
  /** Optional longer sub-text shown below the main message */
  detail?: string
  onConfirm?: () => void
  onEdit?: () => void
  onReject?: () => void
  className?: string
}

export default function AIProposalBanner({
  message = 'AI suggested this value — review before publishing.',
  detail,
  onConfirm,
  onEdit,
  onReject,
  className,
}: AIProposalBannerProps) {
  return (
    <div
      className={cn(
        'relative flex items-start gap-3 px-4 py-3.5 rounded-lg',
        'bg-brand-gradient',
        'border border-primary/20',
        'shadow-sm',
        className,
      )}
      role="status"
      aria-live="polite"
    >
      {/* Accent line on the inline-start edge */}
      <span
        className="absolute inset-y-0 start-0 w-0.5 rounded-full bg-primary"
        aria-hidden="true"
      />

      {/* Icon */}
      <Sparkles
        size={16}
        className="mt-0.5 text-primary shrink-0"
        aria-hidden="true"
      />

      {/* Text block */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-text">{message}</p>
        {detail && (
          <p className="mt-0.5 text-xs text-text-muted">{detail}</p>
        )}
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-1.5 shrink-0 flex-wrap">
        {onConfirm && (
          <button
            onClick={onConfirm}
            aria-label="Confirm AI suggestion"
            className={cn(
              'inline-flex items-center gap-1 px-2.5 py-1 rounded',
              'text-xs font-medium border',
              'bg-success-subtle text-success border-success/25',
              'hover:bg-success/20 focus-visible:ring-2 ring-success',
              'transition-colors duration-fast',
            )}
          >
            <Check size={12} aria-hidden="true" />
            Confirm
          </button>
        )}
        {onEdit && (
          <button
            onClick={onEdit}
            aria-label="Edit AI suggestion"
            className={cn(
              'inline-flex items-center gap-1 px-2.5 py-1 rounded',
              'text-xs font-medium border',
              'bg-surface-raised text-text-muted border-border',
              'hover:bg-border focus-visible:ring-2 ring-primary',
              'transition-colors duration-fast',
            )}
          >
            <Pencil size={12} aria-hidden="true" />
            Edit
          </button>
        )}
        {onReject && (
          <button
            onClick={onReject}
            aria-label="Reject AI suggestion"
            className={cn(
              'inline-flex items-center gap-1 px-2.5 py-1 rounded',
              'text-xs font-medium border',
              'bg-danger-subtle text-danger border-danger/25',
              'hover:bg-danger/20 focus-visible:ring-2 ring-danger',
              'transition-colors duration-fast',
            )}
          >
            <X size={12} aria-hidden="true" />
            Reject
          </button>
        )}
      </div>
    </div>
  )
}
