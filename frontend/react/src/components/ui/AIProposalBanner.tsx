import { Sparkles, Check, Pencil, X } from 'lucide-react'

interface AIProposalBannerProps {
  message?: string
  onConfirm?: () => void
  onEdit?: () => void
  onReject?: () => void
}

export default function AIProposalBanner({
  message = 'AI suggested this value — confirm, edit, or reject.',
  onConfirm,
  onEdit,
  onReject,
}: AIProposalBannerProps) {
  return (
    <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-warning/10 border border-warning/30">
      <Sparkles size={16} className="text-warning shrink-0" />
      <p className="flex-1 text-sm text-warning">{message}</p>
      <div className="flex items-center gap-1 shrink-0">
        {onConfirm && (
          <button
            onClick={onConfirm}
            className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-success bg-success/10 hover:bg-success/20 rounded transition-colors"
          >
            <Check size={12} />
            Confirm
          </button>
        )}
        {onEdit && (
          <button
            onClick={onEdit}
            className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-text-muted bg-surface-raised hover:bg-border-subtle rounded transition-colors"
          >
            <Pencil size={12} />
            Edit
          </button>
        )}
        {onReject && (
          <button
            onClick={onReject}
            className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-danger bg-danger/10 hover:bg-danger/20 rounded transition-colors"
          >
            <X size={12} />
            Reject
          </button>
        )}
      </div>
    </div>
  )
}
