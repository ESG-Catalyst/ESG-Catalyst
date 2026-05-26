import { useState, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Check,
  X,
  Pencil,
  FileText,
  AlertTriangle,
  ChevronRight,
  Sparkles,
  BookOpen,
} from 'lucide-react'
import { getMetrics, updateMetric, type MetricDTO } from '@/api/metrics'
import { generateReport } from '@/api/reports'
import StatusPill from '@/components/ui/StatusPill'
import { usePipelineStore } from '@/store/pipeline'

// ─── Pillar chip ──────────────────────────────────────────────────────────────

const PILLAR_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  E: { bg: 'rgba(16,185,129,0.15)', text: '#10B981', label: 'Environmental' },
  S: { bg: 'rgba(56,189,248,0.15)', text: '#38BDF8', label: 'Social' },
  G: { bg: 'rgba(167,139,250,0.15)', text: '#A78BFA', label: 'Governance' },
}

function PillarChip({ pillar }: { pillar?: string | null }) {
  if (!pillar) return null
  const s = PILLAR_STYLE[pillar]
  if (!s) return null
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold"
      style={{ background: s.bg, color: s.text }}
    >
      {pillar}
    </span>
  )
}

// ─── Confidence bar ───────────────────────────────────────────────────────────

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color =
    pct >= 80 ? '#10B981' : pct >= 50 ? '#F59E0B' : '#EF4444'
  return (
    <div className="flex items-center gap-2">
      <div
        className="flex-1 h-1.5 rounded-full overflow-hidden"
        style={{ background: 'var(--color-border-subtle)' }}
      >
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span
        className="text-xs tabular-nums w-8 text-right"
        style={{ color, fontFamily: 'var(--font-mono)' }}
      >
        {pct}%
      </span>
    </div>
  )
}

// ─── Inline edit form ─────────────────────────────────────────────────────────

function EditForm({
  metric,
  onSave,
  onCancel,
  saving,
}: {
  metric: MetricDTO
  onSave: (value: number | null, unit: string | null, note: string | null) => void
  onCancel: () => void
  saving: boolean
}) {
  const [val, setVal] = useState(metric.value?.toString() ?? '')
  const [unit, setUnit] = useState(metric.unit ?? '')
  const [note, setNote] = useState('')

  const UNIT_SUGGESTIONS = ['GJ', 'tCO2e', 'm3', 'MWh', '%', 'EGP', 'USD', 'employees', 'incidents']

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.2 }}
      className="overflow-hidden"
    >
      <div
        className="mt-3 p-4 rounded-lg space-y-3"
        style={{ background: 'var(--color-bg)', border: '1px solid var(--color-border)' }}
      >
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-text-muted mb-1">Value</label>
            <input
              type="number"
              value={val}
              onChange={(e) => setVal(e.target.value)}
              className="w-full px-3 py-1.5 text-sm rounded"
              style={{
                background: 'var(--color-surface-raised)',
                border: '1px solid var(--color-border)',
                color: 'var(--color-text)',
                fontFamily: 'var(--font-mono)',
              }}
              placeholder="e.g. 19262"
            />
          </div>
          <div>
            <label className="block text-xs text-text-muted mb-1">Unit</label>
            <input
              type="text"
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
              list="unit-suggestions"
              className="w-full px-3 py-1.5 text-sm rounded"
              style={{
                background: 'var(--color-surface-raised)',
                border: '1px solid var(--color-border)',
                color: 'var(--color-text)',
              }}
              placeholder="e.g. tCO2e"
            />
            <datalist id="unit-suggestions">
              {UNIT_SUGGESTIONS.map((u) => <option key={u} value={u} />)}
            </datalist>
          </div>
        </div>
        <div>
          <label className="block text-xs text-text-muted mb-1">Reason for edit</label>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            className="w-full px-3 py-1.5 text-sm rounded resize-none"
            style={{
              background: 'var(--color-surface-raised)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text)',
            }}
            placeholder="Optional note for audit trail"
          />
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() =>
              onSave(
                val !== '' ? parseFloat(val) : null,
                unit || null,
                note || null,
              )
            }
            disabled={saving}
            className="px-4 py-1.5 text-xs font-semibold rounded transition-colors disabled:opacity-50"
            style={{ background: 'var(--color-primary)', color: '#fff' }}
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button
            onClick={onCancel}
            className="px-4 py-1.5 text-xs font-medium rounded transition-colors text-text-muted"
            style={{ background: 'var(--color-surface-raised)' }}
          >
            Cancel
          </button>
        </div>
      </div>
    </motion.div>
  )
}

// ─── Metric card ──────────────────────────────────────────────────────────────

function MetricCard({
  metric,
  selected,
  onClick,
  onApprove,
  onReject,
  onSaveEdit,
  saving,
}: {
  metric: MetricDTO
  selected: boolean
  onClick: () => void
  onApprove: () => void
  onReject: () => void
  onSaveEdit: (value: number | null, unit: string | null, note: string | null) => void
  saving: boolean
}) {
  const [editOpen, setEditOpen] = useState(false)
  const confidence = metric.confidence ?? 0
  const needsReview = confidence < 0.8

  const displayValue =
    metric.value != null
      ? `${metric.value.toLocaleString()}${metric.unit ? ' ' + metric.unit : ''}`
      : metric.original_value ?? '—'

  return (
    <div
      onClick={() => { if (!editOpen) onClick() }}
      className="rounded-xl p-4 cursor-pointer transition-all"
      style={{
        background: selected ? 'rgba(13,148,136,0.07)' : 'var(--color-surface)',
        border: selected
          ? '1px solid rgba(13,148,136,0.45)'
          : '1px solid var(--color-border)',
      }}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className="text-xs font-semibold px-2 py-0.5 rounded"
            style={{
              fontFamily: 'var(--font-mono)',
              color: 'var(--color-primary)',
              background: 'rgba(13,148,136,0.12)',
              border: '1px solid rgba(13,148,136,0.25)',
            }}
          >
            {metric.gri_code}
          </span>
          <PillarChip pillar={metric.pillar} />
        </div>
        <StatusPill status={metric.status as 'extracted' | 'ambiguous' | 'approved' | 'rejected'} />
      </div>

      {/* Label */}
      <p className="text-sm font-medium text-text mb-2 leading-snug">{metric.label}</p>

      {/* Value */}
      <p
        className="text-xl font-bold mb-2"
        style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-primary)' }}
      >
        {displayValue}
      </p>

      {/* Confidence */}
      <div className="mb-3">
        <p className="text-xs text-text-muted mb-1">Confidence</p>
        <ConfidenceBar value={confidence} />
      </div>

      {/* Source */}
      {(metric.source_file || metric.source_page) && (
        <p className="text-xs text-text-subtle mb-3">
          Source:{metric.source_file ? ` ${metric.source_file}` : ''}{metric.source_page ? `, page ${metric.source_page}` : ''}
        </p>
      )}

      {/* Low-confidence banner */}
      {needsReview && metric.status !== 'approved' && metric.status !== 'rejected' && (
        <div
          className="flex items-start gap-2 px-3 py-2 rounded-lg mb-3 text-xs"
          style={{ background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.3)', color: '#F59E0B' }}
        >
          <Sparkles size={13} className="mt-0.5 shrink-0" />
          <span>AI confidence is {Math.round(confidence * 100)}% — please verify this value before approving.</span>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
        <button
          onClick={onApprove}
          disabled={metric.status === 'approved' || saving}
          className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded border transition-colors disabled:opacity-40"
          style={{
            borderColor: metric.status === 'approved' ? '#10B981' : 'rgba(16,185,129,0.4)',
            color: metric.status === 'approved' ? '#10B981' : 'rgba(16,185,129,0.8)',
            background: metric.status === 'approved' ? 'rgba(16,185,129,0.12)' : 'transparent',
          }}
        >
          <Check size={12} />
          {metric.status === 'approved' ? 'Approved' : 'Approve'}
        </button>
        <button
          onClick={onReject}
          disabled={metric.status === 'rejected' || saving}
          className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded border transition-colors disabled:opacity-40"
          style={{
            borderColor: metric.status === 'rejected' ? '#EF4444' : 'rgba(239,68,68,0.4)',
            color: metric.status === 'rejected' ? '#EF4444' : 'rgba(239,68,68,0.8)',
            background: metric.status === 'rejected' ? 'rgba(239,68,68,0.12)' : 'transparent',
          }}
        >
          <X size={12} />
          {metric.status === 'rejected' ? 'Rejected' : 'Reject'}
        </button>
        <button
          onClick={() => setEditOpen((o) => !o)}
          className="flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded border transition-colors"
          style={{
            borderColor: editOpen ? 'var(--color-primary)' : 'var(--color-border)',
            color: editOpen ? 'var(--color-primary)' : 'var(--color-text-muted)',
            background: editOpen ? 'rgba(13,148,136,0.08)' : 'transparent',
          }}
        >
          <Pencil size={12} />
          Edit
        </button>
      </div>

      {/* Edit form */}
      <AnimatePresence>
        {editOpen && (
          <EditForm
            metric={metric}
            saving={saving}
            onSave={(v, u, n) => {
              onSaveEdit(v, u, n)
              setEditOpen(false)
            }}
            onCancel={() => setEditOpen(false)}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

// ─── Evidence viewer ──────────────────────────────────────────────────────────

function EvidenceViewer({ metric }: { metric: MetricDTO | null }) {
  if (!metric) {
    return (
      <div
        className="rounded-xl p-6 h-full flex flex-col items-center justify-center text-center gap-3"
        style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
      >
        <BookOpen size={28} style={{ color: 'var(--color-text-subtle)' }} />
        <p className="text-sm text-text-muted">Select a metric to view source evidence</p>
      </div>
    )
  }

  const evidence = metric.evidence_chunk
  const displayValue =
    metric.value != null ? String(metric.value) : metric.original_value ?? null

  // Highlight the numeric value inside the evidence text
  function highlightEvidence(text: string, highlight: string | null): React.ReactNode {
    if (!highlight) return text
    const escaped = highlight.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const parts = text.split(new RegExp(`(${escaped})`, 'gi'))
    return parts.map((part, i) =>
      new RegExp(`^${escaped}$`, 'i').test(part) ? (
        <mark
          key={i}
          style={{ background: 'rgba(13,148,136,0.3)', color: 'var(--color-primary)', borderRadius: 2, padding: '0 2px' }}
        >
          {part}
        </mark>
      ) : (
        part
      ),
    )
  }

  return (
    <div
      className="rounded-xl p-5 sticky top-6 flex flex-col gap-4"
      style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
    >
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-1">
          Source Evidence
        </p>
        {evidence ? (
          <p
            className="text-sm leading-relaxed text-text rounded-lg p-3"
            style={{ background: 'var(--color-bg)', border: '1px solid var(--color-border)' }}
          >
            {highlightEvidence(evidence, displayValue)}
          </p>
        ) : (
          <p className="text-sm text-text-subtle italic">No evidence text available for this metric.</p>
        )}
      </div>

      {(metric.source_file || metric.source_page) && (
        <p className="text-xs text-text-muted">
          <FileText size={11} className="inline mr-1 mb-0.5" />
          {metric.source_file && <span>{metric.source_file}</span>}
          {metric.source_page && <span> · Page {metric.source_page}</span>}
        </p>
      )}

      <div
        className="rounded-lg p-4"
        style={{ background: 'var(--color-bg)', border: '1px solid var(--color-border)' }}
      >
        <p className="text-xs font-semibold text-text mb-1">
          {metric.gri_code} — {metric.label}
        </p>
        {metric.fra_code && (
          <p className="text-xs text-text-muted mb-0.5">
            FRA Code: <span style={{ fontFamily: 'var(--font-mono)' }}>{metric.fra_code}</span>
          </p>
        )}
        {metric.sasb_code && (
          <p className="text-xs text-text-muted mb-0.5">
            SASB Code: <span style={{ fontFamily: 'var(--font-mono)' }}>{metric.sasb_code}</span>
          </p>
        )}
        {metric.topic && (
          <p className="text-xs text-text-subtle mt-2">
            Required for: {metric.topic} · GRI Universal Standards
            {metric.fra_code ? ' / FRA Decree 108' : ''}
          </p>
        )}
      </div>
    </div>
  )
}

// ─── Stats bar ────────────────────────────────────────────────────────────────

function StatCard({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <div
      className="rounded-lg px-4 py-3 flex flex-col gap-0.5"
      style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
    >
      <span className="text-2xl font-bold" style={{ color: color ?? 'var(--color-text)', fontFamily: 'var(--font-mono)' }}>
        {value}
      </span>
      <span className="text-xs text-text-muted">{label}</span>
    </div>
  )
}

// ─── Skeleton ─────────────────────────────────────────────────────────────────

function Skeleton({ className = '' }: { className?: string }) {
  return (
    <div
      className={`rounded animate-pulse ${className}`}
      style={{ background: 'var(--color-surface-raised)' }}
    />
  )
}

// ─── Sort order ───────────────────────────────────────────────────────────────

function sortPriority(m: MetricDTO): number {
  if (m.status === 'ambiguous' || (m.status === 'extracted' && m.confidence < 0.8)) return 0
  if (m.status === 'extracted') return 1
  if (m.status === 'approved') return 2
  return 3 // rejected / missing
}

// ─── Page ─────────────────────────────────────────────────────────────────────

type FilterTab = 'all' | 'review' | 'approved' | 'rejected'

export default function Results() {
  const { documentId: paramDocId } = useParams<{ documentId: string }>()
  const { documentId: storedDocId } = usePipelineStore()
  const documentId = paramDocId ?? storedDocId ?? undefined
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [filterTab, setFilterTab] = useState<FilterTab>('all')
  const [search, setSearch] = useState('')
  const [pillarFilter, setPillarFilter] = useState<string | null>(null)
  const [generatingReport, setGeneratingReport] = useState(false)

  const { data: metrics = [], isLoading } = useQuery({
    queryKey: ['metrics', documentId],
    queryFn: () => getMetrics(documentId!),
    enabled: !!documentId,
  })

  const mutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof updateMetric>[1] }) =>
      updateMetric(id, data),
    onSuccess: (updated) => {
      queryClient.setQueryData<MetricDTO[]>(['metrics', documentId], (old) =>
        old ? old.map((m) => (m.id === updated.id ? updated : m)) : old,
      )
    },
  })

  // Derived stats
  const total = metrics.length
  const approved = metrics.filter((m) => m.status === 'approved').length
  const pendingReview = metrics.filter((m) => m.status !== 'approved' && m.status !== 'rejected' && m.confidence < 0.8).length
  const rejected = metrics.filter((m) => m.status === 'rejected').length

  // Filtered + sorted list
  const filtered = useMemo(() => {
    let list = [...metrics]

    if (filterTab === 'review') list = list.filter((m) => m.status !== 'approved' && m.status !== 'rejected' && m.confidence < 0.8)
    else if (filterTab === 'approved') list = list.filter((m) => m.status === 'approved')
    else if (filterTab === 'rejected') list = list.filter((m) => m.status === 'rejected')

    if (pillarFilter) list = list.filter((m) => m.pillar === pillarFilter)

    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter((m) => m.gri_code.toLowerCase().includes(q) || m.label.toLowerCase().includes(q))
    }

    list.sort((a, b) => sortPriority(a) - sortPriority(b))
    return list
  }, [metrics, filterTab, pillarFilter, search])

  // Auto-select first card when list changes and nothing is selected
  const selectedMetric = metrics.find((m) => m.id === selectedId) ?? filtered[0] ?? null

  function handleApprove(m: MetricDTO) {
    mutation.mutate({ id: m.id, data: { status: 'approved' } })
  }

  function handleReject(m: MetricDTO) {
    mutation.mutate({ id: m.id, data: { status: 'rejected' } })
  }

  function handleSaveEdit(m: MetricDTO, value: number | null, unit: string | null, note: string | null) {
    mutation.mutate({ id: m.id, data: { value, unit, note, status: 'approved' } })
  }

  async function handleGenerateReport() {
    if (!documentId || approved === 0 || generatingReport) return
    setGeneratingReport(true)
    try {
      const job = await generateReport({ document_id: documentId })
      navigate(`/report/${job.report_id}?doc=${documentId}`)
    } catch {
      setGeneratingReport(false)
    }
  }

  const TABS: { id: FilterTab; label: string; count?: number }[] = [
    { id: 'all', label: 'All', count: total },
    { id: 'review', label: 'Needs Review', count: pendingReview },
    { id: 'approved', label: 'Approved', count: approved },
    { id: 'rejected', label: 'Rejected', count: rejected },
  ]

  const PILLARS = ['E', 'S', 'G'] as const

  // A bulk approve/reject is only meaningful for rows the LLM actually
  // surfaced for review. 'missing' rows have no value to approve — letting
  // them flip to 'approved' makes the scorer treat absent data as a full
  // disclosure (see scorer._legacy_score_indicator). 'approved' / 'rejected'
  // are already terminal for bulk purposes.
  const bulkActionable = filtered.filter(
    (m) => m.status === 'extracted' || m.status === 'ambiguous',
  )

  function handleApproveAll() {
    bulkActionable.forEach((m) =>
      mutation.mutate({ id: m.id, data: { status: 'approved' } }),
    )
  }

  function handleRejectAll() {
    bulkActionable.forEach((m) =>
      mutation.mutate({ id: m.id, data: { status: 'rejected' } }),
    )
  }

  if (!documentId) {
    return (
      <div className="p-6 text-text-muted text-sm">No document selected.</div>
    )
  }

  return (
    <div className="flex flex-col min-h-screen" style={{ paddingBottom: '5rem' }}>
      {/* Header */}
      <div className="px-6 pt-6 pb-4">
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-1">
          Metric Review
        </p>
        <h1 className="text-2xl font-semibold text-text">Review Extracted Metrics</h1>
        <p className="text-sm text-text-muted mt-1 max-w-xl">
          Review and approve AI-extracted metrics before generating your report.
          Metrics with confidence &lt; 80% require review.
        </p>
      </div>

      {/* Stats bar */}
      <div className="px-6 pb-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-16" />)
        ) : (
          <>
            <StatCard label="Total Extracted" value={total} />
            <StatCard label="Approved" value={approved} color="#10B981" />
            <StatCard label="Needs Review" value={pendingReview} color="#F59E0B" />
            <StatCard label="Rejected" value={rejected} color="#EF4444" />
          </>
        )}
      </div>

      {/* Filter bar */}
      <div className="px-6 pb-4 flex flex-wrap items-center gap-3">
        {/* Status tabs */}
        <div
          className="flex items-center rounded-lg p-1 gap-0.5"
          style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
        >
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setFilterTab(tab.id)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded transition-colors"
              style={{
                background: filterTab === tab.id ? 'var(--color-primary)' : 'transparent',
                color: filterTab === tab.id ? '#fff' : 'var(--color-text-muted)',
              }}
            >
              {tab.label}
              {tab.count !== undefined && (
                <span
                  className="px-1.5 py-0.5 rounded-full text-xs"
                  style={{
                    background: filterTab === tab.id ? 'rgba(255,255,255,0.2)' : 'var(--color-surface-raised)',
                    color: filterTab === tab.id ? '#fff' : 'var(--color-text-muted)',
                  }}
                >
                  {tab.count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Pillar filter — E / S / G chips */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setPillarFilter(null)}
            className="px-3 py-1.5 text-xs font-medium rounded-lg transition-colors"
            style={{
              background: pillarFilter === null ? 'var(--color-surface-raised)' : 'transparent',
              color: pillarFilter === null ? 'var(--color-text)' : 'var(--color-text-muted)',
              border: `1px solid ${pillarFilter === null ? 'var(--color-primary)' : 'var(--color-border)'}`,
            }}
          >
            All pillars
          </button>
          {PILLARS.map((p) => {
            const s = PILLAR_STYLE[p]
            const active = pillarFilter === p
            return (
              <button
                key={p}
                onClick={() => setPillarFilter(active ? null : p)}
                className="px-3 py-1.5 text-xs font-semibold rounded-lg transition-all"
                style={{
                  background: active ? s.bg : 'transparent',
                  color: active ? s.text : 'var(--color-text-muted)',
                  border: `1.5px solid ${active ? s.text : 'var(--color-border)'}`,
                  boxShadow: active ? `0 0 0 2px ${s.text}22` : undefined,
                }}
              >
                {p} — {s.label}
              </button>
            )
          })}
        </div>

        {/* Search */}
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search GRI code or indicator…"
          className="flex-1 min-w-40 px-3 py-1.5 text-sm rounded-lg"
          style={{
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            color: 'var(--color-text)',
          }}
        />

        {/* Bulk actions — only operate on pending-review rows
            (extracted / ambiguous). 'missing' rows have no value so
            sweeping them to approved would inflate the score. */}
        {bulkActionable.length > 0 && (
          <div className="flex items-center gap-1.5 ml-auto">
            <button
              onClick={handleApproveAll}
              disabled={mutation.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg border transition-colors disabled:opacity-40"
              style={{
                borderColor: 'rgba(16,185,129,0.5)',
                color: '#10B981',
                background: 'rgba(16,185,129,0.08)',
              }}
              title={`Approve the ${bulkActionable.length} pending-review metric(s) (extracted / ambiguous). Missing rows are skipped.`}
            >
              <Check size={12} />
              Approve all ({bulkActionable.length})
            </button>
            <button
              onClick={handleRejectAll}
              disabled={mutation.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg border transition-colors disabled:opacity-40"
              style={{
                borderColor: 'rgba(239,68,68,0.5)',
                color: '#EF4444',
                background: 'rgba(239,68,68,0.08)',
              }}
              title={`Reject the ${bulkActionable.length} pending-review metric(s) (extracted / ambiguous). Missing rows are skipped.`}
            >
              <X size={12} />
              Reject all ({bulkActionable.length})
            </button>
          </div>
        )}
      </div>

      {/* Two-column layout */}
      <div className="flex-1 px-6 grid lg:grid-cols-[3fr_2fr] gap-6 items-start">
        {/* Left — metrics list */}
        <div className="space-y-3">
          {isLoading ? (
            Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-48 rounded-xl" />)
          ) : filtered.length === 0 ? (
            <div
              className="rounded-xl p-10 flex flex-col items-center text-center gap-3"
              style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
            >
              <AlertTriangle size={28} style={{ color: 'var(--color-text-subtle)' }} />
              <p className="text-sm text-text-muted">No metrics match the current filters.</p>
            </div>
          ) : (
            filtered.map((m) => (
              <MetricCard
                key={m.id}
                metric={m}
                selected={selectedMetric?.id === m.id}
                onClick={() => setSelectedId(m.id)}
                onApprove={() => handleApprove(m)}
                onReject={() => handleReject(m)}
                onSaveEdit={(v, u, n) => handleSaveEdit(m, v, u, n)}
                saving={mutation.isPending && mutation.variables?.id === m.id}
              />
            ))
          )}
        </div>

        {/* Right — evidence viewer */}
        <div className="hidden lg:block">
          <EvidenceViewer metric={selectedMetric} />
        </div>
      </div>

      {/* Fixed bottom action bar */}
      <div
        className="fixed bottom-0 left-0 right-0 z-20 px-6 py-3 flex items-center justify-between"
        style={{
          background: 'rgba(11,18,32,0.95)',
          backdropFilter: 'blur(12px)',
          borderTop: '1px solid var(--color-border)',
        }}
      >
        <p className="text-sm text-text-muted">
          <span className="font-semibold text-text">{approved}</span> of{' '}
          <span className="font-semibold text-text">{total}</span> indicators reviewed
          {pendingReview > 0 && (
            <span className="ml-2 text-amber-400">
              · {pendingReview} need{pendingReview === 1 ? 's' : ''} review
            </span>
          )}
        </p>
        <button
          onClick={handleGenerateReport}
          disabled={approved === 0 || generatingReport}
          className="flex items-center gap-2 px-6 py-2.5 text-sm font-semibold rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          style={{ background: 'var(--color-primary)', color: '#fff' }}
          onMouseEnter={(e) => { if (!e.currentTarget.disabled) e.currentTarget.style.background = 'var(--color-primary-hover)' }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--color-primary)' }}
        >
          {generatingReport && (
            <svg className="animate-spin" width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path d="M21 12a9 9 0 1 1-6.219-8.56" strokeLinecap="round" />
            </svg>
          )}
          Generate Report
          {!generatingReport && <ChevronRight size={15} />}
        </button>
      </div>
    </div>
  )
}
