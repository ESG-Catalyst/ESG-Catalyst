import StatusPill from './StatusPill'
import type { StatusValue } from './StatusPill'

export interface MetricRow {
  id: string
  gri_code: string
  label: string
  value?: number | null
  unit?: string | null
  confidence: number
  status: StatusValue
  pillar?: string | null
}

interface MetricTableProps {
  rows?: MetricRow[]
  onApprove?: (id: string) => void
  onReject?: (id: string) => void
}

export default function MetricTable({ rows = [], onApprove, onReject }: MetricTableProps) {
  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-surface-raised">
            <th className="text-left px-4 py-2.5 text-text-muted font-medium">GRI Code</th>
            <th className="text-left px-4 py-2.5 text-text-muted font-medium">Label</th>
            <th className="text-left px-4 py-2.5 text-text-muted font-medium">Value</th>
            <th className="text-left px-4 py-2.5 text-text-muted font-medium">Confidence</th>
            <th className="text-left px-4 py-2.5 text-text-muted font-medium">Status</th>
            {(onApprove || onReject) && (
              <th className="text-left px-4 py-2.5 text-text-muted font-medium">Actions</th>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={6} className="px-4 py-8 text-center text-text-muted">
                No metrics yet.
              </td>
            </tr>
          )}
          {rows.map((row) => (
            <tr key={row.id} className="border-b border-border last:border-0 hover:bg-surface-raised/50 transition-colors">
              <td className="px-4 py-2.5 font-mono text-xs text-text-muted">{row.gri_code}</td>
              <td className="px-4 py-2.5 text-text">{row.label}</td>
              <td className="px-4 py-2.5 text-text">
                {row.value != null ? `${row.value}${row.unit ? ` ${row.unit}` : ''}` : <span className="text-text-subtle">—</span>}
              </td>
              <td className="px-4 py-2.5">
                <ConfidenceBar value={row.confidence} />
              </td>
              <td className="px-4 py-2.5">
                <StatusPill status={row.status} />
              </td>
              {(onApprove || onReject) && (
                <td className="px-4 py-2.5">
                  <div className="flex gap-2">
                    {onApprove && (
                      <button
                        onClick={() => onApprove(row.id)}
                        className="text-xs px-2 py-1 bg-success/10 text-success rounded hover:bg-success/20 transition-colors"
                      >
                        Approve
                      </button>
                    )}
                    {onReject && (
                      <button
                        onClick={() => onReject(row.id)}
                        className="text-xs px-2 py-1 bg-danger/10 text-danger rounded hover:bg-danger/20 transition-colors"
                      >
                        Reject
                      </button>
                    )}
                  </div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = pct >= 80 ? 'bg-success' : pct >= 60 ? 'bg-warning' : 'bg-danger'
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 rounded-full bg-border-subtle overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-text-muted tabular-nums">{pct}%</span>
    </div>
  )
}
