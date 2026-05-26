import { useState, useMemo, useCallback, useEffect, useRef } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Download,
  Share2,
  Lock,
  CheckCircle2,
  FileText,
  BarChart2,
  AlertTriangle,
  Loader2,
  Check,
} from 'lucide-react'
import { getReport, getReportPdf } from '@/api/reports'
import { getMetrics, type MetricDTO } from '@/api/metrics'
import ScoreGauge from '@/components/ui/ScoreGauge'
import StatusPill from '@/components/ui/StatusPill'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function TIER_LABEL(score: number): string {
  if (score >= 75) return 'Leading'
  if (score >= 55) return 'Established'
  if (score >= 35) return 'Developing'
  return 'Laggard'
}

function TIER_COLOR(score: number): string {
  if (score >= 75) return '#10B981'
  if (score >= 55) return '#38BDF8'
  if (score >= 35) return '#F59E0B'
  return '#EF4444'
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-GB', { year: 'numeric', month: 'long', day: 'numeric' })
}

// Pillar scores come from the backend ScoringResult (persisted on the
// Report row by the worker). The PDF reads the same numbers — we must
// not recompute here or the dashboard will disagree with the PDF.

// ─── Generating state ─────────────────────────────────────────────────────────

const GEN_STEPS = [
  { label: 'Building report sections', estimateSec: 10 },
  { label: 'Drafting narratives with LLM', estimateSec: 60 },
  { label: 'Rendering PDF', estimateSec: 20 },
]

function GeneratingState() {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const id = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(id)
  }, [])

  // Derive which step we're on based on elapsed time
  const cumulative = GEN_STEPS.reduce<number[]>((acc, s, i) => {
    acc.push((acc[i - 1] ?? 0) + s.estimateSec)
    return acc
  }, [])
  const activeStep = cumulative.findIndex((c) => elapsed < c)
  const isTimedOut = elapsed > 300 // 5 min — surface a friendly warning

  function formatSec(s: number) {
    if (s < 60) return `${s}s`
    return `${Math.floor(s / 60)}m ${s % 60}s`
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-8 max-w-md mx-auto">
      {!isTimedOut ? (
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 1.2, repeat: Infinity, ease: 'linear' }}
        >
          <Loader2 size={44} style={{ color: 'var(--color-primary)' }} />
        </motion.div>
      ) : (
        <AlertTriangle size={44} style={{ color: '#F59E0B' }} />
      )}
      <div className="text-center">
        <p className="text-xl font-semibold text-text mb-1">
          {isTimedOut ? 'Report is taking longer than expected…' : 'Generating your ESG report…'}
        </p>
        <p className="text-sm text-text-muted">
          {isTimedOut
            ? `${formatSec(elapsed)} elapsed. The narrative LLM may be slow or unavailable. The page will update automatically when done.`
            : 'This usually takes 1–2 minutes.'}
        </p>
      </div>
      <div className="space-y-3 w-72">
        {GEN_STEPS.map((step, i) => {
          const isActive = i === activeStep && !isTimedOut
          const isDone = activeStep === -1 || i < activeStep
          return (
            <div key={i} className="flex items-center gap-3">
              {isDone ? (
                <CheckCircle2 size={16} style={{ color: '#10B981' }} className="shrink-0" />
              ) : isActive ? (
                <motion.div
                  animate={{ opacity: [1, 0.3, 1] }}
                  transition={{ duration: 1, repeat: Infinity }}
                  className="shrink-0"
                >
                  <Loader2 size={16} style={{ color: 'var(--color-primary)' }} />
                </motion.div>
              ) : (
                <div
                  className="w-4 h-4 rounded-full border shrink-0"
                  style={{ borderColor: 'var(--color-border)' }}
                />
              )}
              <span
                className="text-sm"
                style={{
                  color: isDone ? '#10B981' : isActive ? 'var(--color-text)' : 'var(--color-text-subtle)',
                }}
              >
                {step.label}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── Framework chip ───────────────────────────────────────────────────────────

const FW_STYLE: Record<string, { bg: string; text: string }> = {
  GRI: { bg: 'rgba(16,185,129,0.15)', text: '#10B981' },
  FRA: { bg: 'rgba(56,189,248,0.15)', text: '#38BDF8' },
  SASB: { bg: 'rgba(167,139,250,0.15)', text: '#A78BFA' },
}

function FwChip({ label }: { label: string }) {
  const s = FW_STYLE[label] ?? { bg: 'var(--color-surface-raised)', text: 'var(--color-text-muted)' }
  return (
    <span
      className="px-2 py-0.5 rounded text-xs font-semibold"
      style={{ background: s.bg, color: s.text }}
    >
      {label}
    </span>
  )
}

// ─── Status workflow ──────────────────────────────────────────────────────────

type ReportStatus = 'draft' | 'in_review' | 'approved' | 'locked' | string

function StatusWorkflow({ status }: { status: ReportStatus }) {
  const [notice, setNotice] = useState<string | null>(null)

  const NEXT: Record<string, { label: string; color: string }> = {
    draft: { label: 'Submit for Review', color: 'var(--color-primary)' },
    in_review: { label: 'Approve', color: '#10B981' },
    approved: { label: 'Lock Report', color: '#A78BFA' },
  }
  const next = NEXT[status.toLowerCase()]
  const pill = (status === 'published' ? 'PUBLISHED' : status.toUpperCase()) as 'DRAFT'

  function handleWorkflowAction() {
    setNotice('Reviewer portal coming in Iteration 4 — share the link with your reviewer for now.')
    setTimeout(() => setNotice(null), 4000)
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-xs text-text-muted">Status:</span>
        <StatusPill status={pill === 'DRAFT' ? 'DRAFT' : pill} />
      </div>
      {next ? (
        <button
          onClick={handleWorkflowAction}
          className="w-full py-1.5 text-xs font-semibold rounded transition-colors"
          style={{ background: `${next.color}22`, color: next.color, border: `1px solid ${next.color}55` }}
        >
          {next.label}
        </button>
      ) : status.toLowerCase() === 'locked' ? (
        <div className="flex items-center gap-1.5 text-xs text-text-muted">
          <Lock size={12} /> Report is locked
        </div>
      ) : null}
      {notice && (
        <p className="text-xs text-text-muted leading-snug pt-1">{notice}</p>
      )}
    </div>
  )
}

// ─── Download helper ──────────────────────────────────────────────────────────

async function downloadPdf(reportId: string, filename: string) {
  const blob = await getReportPdf(reportId)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// ─── CSV export ───────────────────────────────────────────────────────────────

function exportCsv(metrics: MetricDTO[], filename: string) {
  const header = ['GRI Code', 'Indicator', 'Value', 'Unit', 'Confidence', 'Status', 'Source File', 'Source Page']
  const rows = metrics.map((m) => [
    m.gri_code,
    m.label,
    m.value ?? m.original_value ?? '',
    m.unit ?? '',
    `${Math.round(m.confidence * 100)}%`,
    m.status,
    m.source_file ?? '',
    m.source_page ?? '',
  ])
  const csv = [header, ...rows].map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// ─── Preview tab ──────────────────────────────────────────────────────────────

const PILLAR_STYLE: Record<string, { color: string; label: string }> = {
  E: { color: '#10B981', label: 'Environmental' },
  S: { color: '#38BDF8', label: 'Social' },
  G: { color: '#A78BFA', label: 'Governance' },
}

function PreviewTab({ metrics }: { metrics: MetricDTO[] }) {
  const byPillar = useMemo(() => {
    const map: Record<string, MetricDTO[]> = { E: [], S: [], G: [], Other: [] }
    for (const m of metrics) {
      if (m.pillar && map[m.pillar]) map[m.pillar].push(m)
      else map['Other'].push(m)
    }
    return map
  }, [metrics])

  if (!metrics.length) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center">
        <FileText size={28} style={{ color: 'var(--color-text-subtle)' }} />
        <p className="text-sm text-text-muted">No metrics available for preview.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {(['E', 'S', 'G'] as const).map((p) => {
        const list = byPillar[p]
        if (!list.length) return null
        const s = PILLAR_STYLE[p]
        return (
          <div
            key={p}
            className="rounded-xl overflow-hidden"
            style={{ border: '1px solid var(--color-border)' }}
          >
            <div
              className="px-5 py-3 flex items-center gap-2"
              style={{ background: `${s.color}12`, borderBottom: '1px solid var(--color-border)' }}
            >
              <span className="w-2 h-2 rounded-full" style={{ background: s.color }} />
              <h3 className="text-sm font-semibold" style={{ color: s.color }}>{s.label}</h3>
              <span className="ml-auto text-xs text-text-muted">{list.length} indicators</span>
            </div>
            <div className="divide-y" style={{ '--tw-divide-opacity': 1 } as React.CSSProperties}>
              {list.map((m) => (
                <div key={m.id} className="px-5 py-3 flex items-center gap-4">
                  <span
                    className="text-xs font-semibold shrink-0 px-2 py-0.5 rounded"
                    style={{
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--color-primary)',
                      background: 'rgba(13,148,136,0.12)',
                      border: '1px solid rgba(13,148,136,0.25)',
                    }}
                  >
                    {m.gri_code}
                  </span>
                  <span className="flex-1 text-sm text-text truncate">{m.label}</span>
                  <span
                    className="text-sm font-semibold tabular-nums"
                    style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-text)' }}
                  >
                    {m.value != null
                      ? `${m.value.toLocaleString()}${m.unit ? ' ' + m.unit : ''}`
                      : m.original_value ?? '—'}
                  </span>
                  <StatusPill status={m.status as 'approved' | 'extracted' | 'ambiguous' | 'rejected'} />
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ─── Metrics table tab ────────────────────────────────────────────────────────

function MetricsTableTab({ metrics, reportDate }: { metrics: MetricDTO[]; reportDate: string }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-text-muted">{metrics.length} metrics in this report</p>
        <button
          onClick={() => exportCsv(metrics, `esg-metrics-${reportDate}.csv`)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded transition-colors"
          style={{
            background: 'var(--color-surface-raised)',
            color: 'var(--color-text-muted)',
            border: '1px solid var(--color-border)',
          }}
        >
          <Download size={12} />
          Export CSV
        </button>
      </div>
      <div className="overflow-x-auto rounded-xl" style={{ border: '1px solid var(--color-border)' }}>
        <table className="w-full text-sm">
          <thead>
            <tr style={{ background: 'var(--color-surface-raised)', borderBottom: '1px solid var(--color-border)' }}>
              {['GRI Code', 'Indicator', 'Value', 'Unit', 'Confidence', 'Status', 'Source'].map((h) => (
                <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-text-muted whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {metrics.map((m, i) => (
              <tr
                key={m.id}
                style={{
                  background: i % 2 === 0 ? 'var(--color-surface)' : 'var(--color-bg)',
                  borderBottom: '1px solid var(--color-border)',
                }}
              >
                <td className="px-4 py-2.5">
                  <span
                    className="text-xs font-semibold px-2 py-0.5 rounded"
                    style={{
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--color-primary)',
                      background: 'rgba(13,148,136,0.12)',
                    }}
                  >
                    {m.gri_code}
                  </span>
                </td>
                <td className="px-4 py-2.5 max-w-xs">
                  <span className="text-xs text-text line-clamp-2">{m.label}</span>
                </td>
                <td className="px-4 py-2.5">
                  <span
                    className="text-xs tabular-nums font-semibold"
                    style={{ fontFamily: 'var(--font-mono)' }}
                  >
                    {m.value != null ? m.value.toLocaleString() : m.original_value ?? '—'}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-xs text-text-muted">{m.unit ?? '—'}</td>
                <td className="px-4 py-2.5">
                  <ConfidencePill value={m.confidence} />
                </td>
                <td className="px-4 py-2.5">
                  <StatusPill status={m.status as 'approved' | 'extracted' | 'ambiguous' | 'rejected'} />
                </td>
                <td className="px-4 py-2.5 text-xs text-text-muted">
                  {m.source_page ? `p. ${m.source_page}` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ConfidencePill({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = pct >= 80 ? '#10B981' : pct >= 50 ? '#F59E0B' : '#EF4444'
  return (
    <span
      className="text-xs font-semibold tabular-nums px-1.5 py-0.5 rounded"
      style={{ color, background: `${color}18`, fontFamily: 'var(--font-mono)' }}
    >
      {pct}%
    </span>
  )
}

// ─── GRI Content Index tab ────────────────────────────────────────────────────

const GRI_INDICATORS_SAMPLE = [
  { code: 'GRI 2-1', label: 'Organizational details', required: true },
  { code: 'GRI 2-9', label: 'Governance structure', required: true },
  { code: 'GRI 302-1', label: 'Energy consumption within organisation', required: false },
  { code: 'GRI 302-3', label: 'Energy intensity', required: false },
  { code: 'GRI 303-5', label: 'Water consumption', required: false },
  { code: 'GRI 305-1', label: 'Direct (Scope 1) GHG emissions', required: true },
  { code: 'GRI 305-2', label: 'Energy indirect (Scope 2) GHG emissions', required: true },
  { code: 'GRI 305-4', label: 'GHG emissions intensity', required: false },
  { code: 'GRI 401-1', label: 'New employee hires and employee turnover', required: false },
  { code: 'GRI 403-9', label: 'Work-related injuries', required: false },
  { code: 'GRI 405-1', label: 'Diversity of governance bodies and employees', required: true },
  { code: 'GRI 418-1', label: 'Substantiated complaints concerning customer privacy', required: false },
]

type GRIStatus = 'reported' | 'partial' | 'omitted'

function GRIIndexTab({ metrics }: { metrics: MetricDTO[] }) {
  function getStatus(code: string): GRIStatus {
    const m = metrics.find((x) => x.gri_code === code)
    if (!m) return 'omitted'
    if (m.status === 'approved') return 'reported'
    if (m.status === 'extracted' || m.status === 'ambiguous') return 'partial'
    return 'omitted'
  }

  const STATUS_STYLE: Record<GRIStatus, { label: string; color: string; bg: string }> = {
    reported: { label: 'Reported', color: '#10B981', bg: 'rgba(16,185,129,0.12)' },
    partial: { label: 'Partially Reported', color: '#F59E0B', bg: 'rgba(245,158,11,0.12)' },
    omitted: { label: 'Omitted', color: '#EF4444', bg: 'rgba(239,68,68,0.12)' },
  }

  return (
    <div>
      <p className="text-xs text-text-muted mb-4">
        GRI Content Index — disclosure status against GRI Universal Standards and Sector Standards.
      </p>
      <div className="overflow-x-auto rounded-xl" style={{ border: '1px solid var(--color-border)' }}>
        <table className="w-full text-sm">
          <thead>
            <tr style={{ background: 'var(--color-surface-raised)', borderBottom: '1px solid var(--color-border)' }}>
              {['GRI Indicator', 'Disclosure', 'Required', 'Status', 'Page Ref'].map((h) => (
                <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-text-muted whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {GRI_INDICATORS_SAMPLE.map((ind, i) => {
              const st = STATUS_STYLE[getStatus(ind.code)]
              const m = metrics.find((x) => x.gri_code === ind.code)
              return (
                <tr
                  key={ind.code}
                  style={{
                    background: i % 2 === 0 ? 'var(--color-surface)' : 'var(--color-bg)',
                    borderBottom: '1px solid var(--color-border)',
                  }}
                >
                  <td className="px-4 py-2.5">
                    <span
                      className="text-xs font-semibold"
                      style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-primary)' }}
                    >
                      {ind.code}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 max-w-xs">
                    <span className="text-xs text-text">{ind.label}</span>
                  </td>
                  <td className="px-4 py-2.5">
                    {ind.required ? (
                      <span className="text-xs font-medium" style={{ color: '#EF4444' }}>Required</span>
                    ) : (
                      <span className="text-xs text-text-subtle">Voluntary</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    <span
                      className="text-xs font-semibold px-2 py-0.5 rounded"
                      style={{ color: st.color, background: st.bg }}
                    >
                      {st.label}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-xs text-text-muted">
                    {m?.source_page ? `p. ${m.source_page}` : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Gap analysis tab ─────────────────────────────────────────────────────────

interface GapRow {
  code: string
  label: string
  why: string
  difficulty: 'Easy' | 'Medium' | 'Hard'
  dataSource: string
  mandatory: boolean
}

const GAP_TEMPLATES: GapRow[] = [
  {
    code: 'GRI 302-1',
    label: 'Energy consumption',
    why: 'Mandatory under FRA Decree 108 for NBFIs; major input to carbon footprint.',
    difficulty: 'Hard',
    dataSource: 'Electricity + gas utility bills',
    mandatory: true,
  },
  {
    code: 'GRI 303-5',
    label: 'Water consumption',
    why: 'Required by GRI Universal Standards 2021 for material topics.',
    difficulty: 'Hard',
    dataSource: 'Water utility invoices, facilities management system',
    mandatory: true,
  },
  {
    code: 'GRI 305-1',
    label: 'Direct GHG emissions (Scope 1)',
    why: 'Core climate disclosure; prerequisite for net-zero commitment reporting.',
    difficulty: 'Hard',
    dataSource: 'Fuel receipts, fleet records, refrigerant logs',
    mandatory: true,
  },
  {
    code: 'GRI 403-9',
    label: 'Work-related injuries',
    why: 'Required for social pillar; material for insurance sector benchmarking.',
    difficulty: 'Medium',
    dataSource: 'HR safety logs, OHSMS incident reports',
    mandatory: false,
  },
  {
    code: 'GRI 405-1',
    label: 'Board diversity',
    why: 'FRA requires gender diversity disclosure for listed entities.',
    difficulty: 'Easy',
    dataSource: 'Board report, corporate governance section',
    mandatory: true,
  },
  {
    code: 'GRI 418-1',
    label: 'Customer privacy complaints',
    why: 'Growing regulatory focus on data protection; GDPR-equivalent Egyptian law.',
    difficulty: 'Easy',
    dataSource: 'Compliance officer report, CRM complaint log',
    mandatory: false,
  },
]

const DIFF_STYLE: Record<GapRow['difficulty'], { color: string; bg: string }> = {
  Easy: { color: '#10B981', bg: 'rgba(16,185,129,0.12)' },
  Medium: { color: '#F59E0B', bg: 'rgba(245,158,11,0.12)' },
  Hard: { color: '#EF4444', bg: 'rgba(239,68,68,0.12)' },
}

function GapAnalysisTab({ metrics }: { metrics: MetricDTO[] }) {
  const approvedCodes = new Set(metrics.filter((m) => m.status === 'approved').map((m) => m.gri_code))
  const gaps = GAP_TEMPLATES.filter((g) => !approvedCodes.has(g.code))
    .sort((a, b) => Number(b.mandatory) - Number(a.mandatory))

  if (!gaps.length) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center">
        <CheckCircle2 size={32} style={{ color: '#10B981' }} />
        <p className="text-base font-semibold text-text">All tracked indicators reported</p>
        <p className="text-sm text-text-muted">No gaps identified in the current indicator set.</p>
      </div>
    )
  }

  return (
    <div>
      <p className="text-xs text-text-muted mb-4">
        {gaps.length} indicator{gaps.length !== 1 ? 's' : ''} missing from approved disclosures.
        Mandatory regulatory requirements listed first.
      </p>
      <div className="overflow-x-auto rounded-xl" style={{ border: '1px solid var(--color-border)' }}>
        <table className="w-full text-sm">
          <thead>
            <tr style={{ background: 'var(--color-surface-raised)', borderBottom: '1px solid var(--color-border)' }}>
              {['Missing Indicator', 'Why It Matters', 'Difficulty', 'Data Source Needed'].map((h) => (
                <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-text-muted whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {gaps.map((g, i) => {
              const d = DIFF_STYLE[g.difficulty]
              return (
                <tr
                  key={g.code}
                  style={{
                    background: i % 2 === 0 ? 'var(--color-surface)' : 'var(--color-bg)',
                    borderBottom: '1px solid var(--color-border)',
                  }}
                >
                  <td className="px-4 py-3">
                    <div className="flex items-start gap-2">
                      {g.mandatory && (
                        <AlertTriangle size={12} style={{ color: '#EF4444', marginTop: 2 }} className="shrink-0" />
                      )}
                      <div>
                        <span
                          className="block text-xs font-semibold"
                          style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-primary)' }}
                        >
                          {g.code}
                        </span>
                        <span className="text-xs text-text">{g.label}</span>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 max-w-xs">
                    <span className="text-xs text-text-muted leading-relaxed">{g.why}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className="text-xs font-semibold px-2 py-0.5 rounded whitespace-nowrap"
                      style={{ color: d.color, background: d.bg }}
                    >
                      {g.difficulty}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs text-text-muted">{g.dataSource}</span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

type Tab = 'preview' | 'metrics' | 'gri' | 'gaps'

const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
  { id: 'preview', label: 'Preview', icon: FileText },
  { id: 'metrics', label: 'Metrics Table', icon: BarChart2 },
  { id: 'gri', label: 'GRI Content Index', icon: CheckCircle2 },
  { id: 'gaps', label: 'Gap Analysis', icon: AlertTriangle },
]

// ─── Resizable split pane hooks ───────────────────────────────────────────────

/** Outer horizontal split — measures against full window width. */
function useResizable(initialPct: number, minPct = 25, maxPct = 75) {
  const [leftPct, setLeftPct] = useState(initialPct)
  const [isDragging, setIsDragging] = useState(false)

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      setIsDragging(true)
      const startX = e.clientX
      const startPct = leftPct

      const onMouseMove = (ev: MouseEvent) => {
        const dx = ev.clientX - startX
        const containerWidth = document.body.clientWidth
        const delta = (dx / containerWidth) * 100
        setLeftPct(Math.min(maxPct, Math.max(minPct, startPct + delta)))
      }

      const onMouseUp = () => {
        setIsDragging(false)
        window.removeEventListener('mousemove', onMouseMove)
        window.removeEventListener('mouseup', onMouseUp)
      }

      window.addEventListener('mousemove', onMouseMove)
      window.addEventListener('mouseup', onMouseUp)
    },
    [leftPct, minPct, maxPct],
  )

  return { leftPct, onMouseDown, isDragging }
}

/** Inner horizontal split — measures against a specific container element. */
function useResizableInner(
  containerRef: React.RefObject<HTMLDivElement | null>,
  initialPct: number,
  minPct = 18,
  maxPct = 55,
) {
  const [leftPct, setLeftPct] = useState(initialPct)
  const [isDragging, setIsDragging] = useState(false)

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      setIsDragging(true)
      const startX = e.clientX
      const startPct = leftPct

      const onMouseMove = (ev: MouseEvent) => {
        const containerWidth = containerRef.current?.clientWidth ?? document.body.clientWidth
        const dx = ev.clientX - startX
        const delta = (dx / containerWidth) * 100
        setLeftPct(Math.min(maxPct, Math.max(minPct, startPct + delta)))
      }

      const onMouseUp = () => {
        setIsDragging(false)
        window.removeEventListener('mousemove', onMouseMove)
        window.removeEventListener('mouseup', onMouseUp)
      }

      window.addEventListener('mousemove', onMouseMove)
      window.addEventListener('mouseup', onMouseUp)
    },
    [leftPct, minPct, maxPct, containerRef],
  )

  return { leftPct, onMouseDown, isDragging }
}

// ─── PDF Preview panel ────────────────────────────────────────────────────────

function PdfPreview({ reportId }: { reportId: string }) {
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let url: string | null = null
    getReportPdf(reportId)
      .then((blob) => {
        url = URL.createObjectURL(blob)
        setPdfUrl(url)
      })
      .catch((err) => {
        setError(err?.message || 'Failed to load PDF')
      })
    return () => {
      if (url) URL.revokeObjectURL(url)
    }
  }, [reportId])

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-center p-6">
        <AlertTriangle size={28} style={{ color: '#EF4444' }} />
        <p className="text-sm text-text-muted">Could not load PDF preview</p>
        <p className="text-xs text-text-subtle">{error}</p>
      </div>
    )
  }

  if (!pdfUrl) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3">
        <Loader2 size={24} className="animate-spin" style={{ color: 'var(--color-primary)' }} />
        <p className="text-xs text-text-muted">Loading PDF…</p>
      </div>
    )
  }

  return (
    <iframe
      // #toolbar=0 hides Chrome's built-in PDF toolbar; view=FitH fits width
      src={`${pdfUrl}#toolbar=0&navpanes=0&scrollbar=0&view=FitH`}
      title="PDF Preview"
      style={{
        width: '100%',
        height: '100%',
        border: 'none',
        display: 'block',
        // Dark neutral matches standard PDF viewer background
        background: '#525659',
      }}
    />
  )
}

export default function ReportView() {
  const { reportId } = useParams<{ reportId: string }>()
  const [searchParams] = useSearchParams()
  const docId = searchParams.get('doc')
  const [activeTab, setActiveTab] = useState<Tab>('preview')
  const [downloading, setDownloading] = useState(false)
  const [copied, setCopied] = useState(false)

  // Outer split: left panel (sidebar+tabs) vs right panel (PDF preview)
  const { leftPct, onMouseDown, isDragging } = useResizable(58)

  // Inner split: sidebar (ESG Score/Actions) vs tab content area
  const leftPanelRef = useRef<HTMLDivElement>(null)
  const {
    leftPct: innerLeftPct,
    onMouseDown: onInnerMouseDown,
    isDragging: isInnerDragging,
  } = useResizableInner(leftPanelRef, 32)

  const { data: report } = useQuery({
    queryKey: ['report', reportId],
    queryFn: () => getReport(reportId!),
    enabled: !!reportId,
    refetchInterval: (query) => {
      const s = query.state.data?.status
      // Backend uses "published" for done; "draft" means failed/reset
      if (s === 'published' || s === 'draft') return false
      return 3000
    },
  })

  // "published" = PDF ready; "draft" = generation failed/reset; anything else = still generating
  const isDone = report?.status === 'published' || report?.status === 'draft'
  const isGenerating = !report || !isDone

  const { data: metrics = [] } = useQuery({
    queryKey: ['metrics-by-doc', docId],
    queryFn: () => getMetrics(docId!),
    enabled: !!docId && !isGenerating,
  })

  // Scores come straight from the persisted Report row — same fields the
  // PDF renders from (see backend/app/workers/tasks.py::_generate_report_async).
  // Backend stores 0–100 floats; coerce nulls to 0 and round for the gauge.
  const scores = useMemo(() => ({
    E: Math.round(report?.environmental_score ?? 0),
    S: Math.round(report?.social_score ?? 0),
    G: Math.round(report?.governance_score ?? 0),
    overall: Math.round(report?.total_score ?? 0),
  }), [report])

  const reportDate = report?.created_at ? new Date(report.created_at).toISOString().slice(0, 10) : 'report'
  const pdfFilename = `esg-report-${reportDate}.pdf`

  const handleDownload = useCallback(async () => {
    if (!reportId || downloading) return
    setDownloading(true)
    try {
      await downloadPdf(reportId, pdfFilename)
    } finally {
      setDownloading(false)
    }
  }, [reportId, downloading, pdfFilename])

  const handleShare = useCallback(() => {
    navigator.clipboard.writeText(window.location.href).catch(() => {})
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [])

  if (!reportId) {
    return <div className="p-6 text-text-muted text-sm">No report selected.</div>
  }

  if (isGenerating) {
    return (
      <div className="p-6">
        <GeneratingState />
      </div>
    )
  }

  return (
    <div
      className="flex h-screen overflow-hidden"
      style={{ cursor: isDragging || isInnerDragging ? 'col-resize' : undefined }}
    >
      {/* ─── Left panel: sidebar (ESG Score) + inner divider + tabs ─── */}
      <div
        ref={leftPanelRef}
        className="flex h-full overflow-hidden shrink-0"
        style={{ width: `${leftPct}%` }}
      >
        {/* ── Sidebar (ESG Score, Actions, Workflow) ── */}
        <aside
          className="shrink-0 flex flex-col gap-4 overflow-y-auto p-4"
          style={{
            width: `${innerLeftPct}%`,
            minWidth: 180,
            borderRight: '1px solid var(--color-border)',
            background: 'var(--color-surface)',
          }}
        >
          {/* Metadata */}
          <div
            className="rounded-xl p-3 space-y-2"
            style={{ background: 'var(--color-bg)', border: '1px solid var(--color-border)' }}
          >
            <div>
              <p className="text-xs text-text-muted mb-0.5">Institution</p>
              <p className="text-sm font-semibold text-text">ESG Company</p>
            </div>
            <div>
              <p className="text-xs text-text-muted mb-0.5">Report Date</p>
              <p className="text-xs text-text">{report ? formatDate(report.created_at) : '—'}</p>
            </div>
            <div>
              <p className="text-xs text-text-muted mb-0.5">Report ID</p>
              <p
                className="text-xs text-text-subtle break-all"
                style={{ fontFamily: 'var(--font-mono)' }}
              >
                {reportId}
              </p>
            </div>
            <div className="flex items-center gap-1 flex-wrap">
              <FwChip label="GRI" />
              <FwChip label="FRA" />
              <FwChip label="SASB" />
            </div>
          </div>

          {/* Score summary */}
          <div
            className="rounded-xl p-3"
            style={{ background: 'var(--color-bg)', border: '1px solid var(--color-border)' }}
          >
            <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-3">
              ESG Score
            </p>
            <ScoreGauge scores={scores} overall={scores.overall} size="sm" />
            <div className="mt-3 text-center">
              <span
                className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold"
                style={{
                  background: `${TIER_COLOR(scores.overall)}18`,
                  color: TIER_COLOR(scores.overall),
                  border: `1px solid ${TIER_COLOR(scores.overall)}44`,
                }}
              >
                {TIER_LABEL(scores.overall)}
              </span>
            </div>
          </div>

          {/* Actions */}
          <div className="space-y-2">
            <button
              onClick={handleDownload}
              disabled={downloading}
              className="w-full flex items-center justify-center gap-2 py-2 text-xs font-semibold rounded-lg transition-colors disabled:opacity-60"
              style={{ background: 'var(--color-primary)', color: '#fff' }}
              onMouseEnter={(e) => { if (!e.currentTarget.disabled) e.currentTarget.style.background = 'var(--color-primary-hover)' }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--color-primary)' }}
            >
              {downloading ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
              Download PDF
            </button>

            <button
              onClick={handleShare}
              className="w-full flex items-center justify-center gap-2 py-2 text-xs font-medium rounded-lg transition-colors"
              style={{
                background: 'transparent',
                color: copied ? '#10B981' : 'var(--color-text-muted)',
                border: `1px solid ${copied ? 'rgba(16,185,129,0.4)' : 'var(--color-border)'}`,
              }}
            >
              {copied ? <Check size={13} /> : <Share2 size={13} />}
              {copied ? 'Link copied!' : 'Share with Reviewer'}
            </button>
            {copied && (
              <p className="text-xs text-center text-text-subtle">Coming soon — reviewer portal not yet live.</p>
            )}
          </div>

          {/* Status workflow */}
          <div
            className="rounded-xl p-3"
            style={{ background: 'var(--color-bg)', border: '1px solid var(--color-border)' }}
          >
            <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-2">
              Workflow
            </p>
            <StatusWorkflow status={report?.status ?? 'complete'} />
          </div>
        </aside>

        {/* ── Inner drag handle: sidebar ↔ disclosure tabs ── */}
        <div
          onMouseDown={onInnerMouseDown}
          className="shrink-0 flex items-center justify-center"
          style={{
            width: 8,
            cursor: 'col-resize',
            background: isInnerDragging ? 'rgba(13,148,136,0.15)' : 'var(--color-border)',
            transition: isInnerDragging ? 'none' : 'background 0.15s',
            zIndex: 10,
          }}
          title="Drag to resize"
        >
          <div
            className="w-1 h-10 rounded-full transition-colors"
            style={{
              background: isInnerDragging ? 'var(--color-primary)' : 'var(--color-text-subtle)',
              opacity: isInnerDragging ? 1 : 0.4,
            }}
          />
        </div>

        {/* ── Disclosure Report tabs ── */}
        <main className="flex-1 p-5 min-w-0 overflow-y-auto">
          {/* Page header */}
          <div className="mb-5">
            <p className="text-xs font-semibold uppercase tracking-widest text-text-muted mb-1">
              Report
            </p>
            <h1 className="text-xl font-semibold text-text">ESG Disclosure Report</h1>
            <p className="text-sm text-text-muted mt-1">
              {report ? formatDate(report.created_at) : ''}
              {metrics.length > 0 && ` · ${metrics.filter((m) => m.status === 'approved').length} approved metrics`}
            </p>
          </div>

          {/* Tab bar */}
          <div
            className="flex items-center gap-1 rounded-xl p-1 mb-5 flex-wrap"
            style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
          >
            {TABS.map((tab) => {
              const Icon = tab.icon
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors"
                  style={{
                    background: activeTab === tab.id ? 'var(--color-primary)' : 'transparent',
                    color: activeTab === tab.id ? '#fff' : 'var(--color-text-muted)',
                  }}
                >
                  <Icon size={12} />
                  {tab.label}
                </button>
              )
            })}
          </div>

          {/* Tab content */}
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.18 }}
            >
              {activeTab === 'preview' && <PreviewTab metrics={metrics} />}
              {activeTab === 'metrics' && <MetricsTableTab metrics={metrics} reportDate={reportDate} />}
              {activeTab === 'gri' && <GRIIndexTab metrics={metrics} />}
              {activeTab === 'gaps' && <GapAnalysisTab metrics={metrics} />}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      {/* ─── Drag handle ─── */}
      <div
        onMouseDown={onMouseDown}
        className="shrink-0 flex items-center justify-center group"
        style={{
          width: 8,
          cursor: 'col-resize',
          background: isDragging ? 'rgba(13,148,136,0.15)' : 'var(--color-border)',
          transition: isDragging ? 'none' : 'background 0.15s',
        }}
        title="Drag to resize"
      >
        <div
          className="w-1 h-10 rounded-full transition-colors"
          style={{
            background: isDragging ? 'var(--color-primary)' : 'var(--color-text-subtle)',
            opacity: isDragging ? 1 : 0.4,
          }}
        />
      </div>

      {/* ─── Right panel: PDF preview ─── */}
      <div
        className="flex-1 min-w-0 h-full flex flex-col"
        style={{ background: '#525659' }}
      >
        <div
          className="px-4 py-2.5 flex items-center gap-2 shrink-0"
          style={{
            background: 'var(--color-surface)',
            borderBottom: '1px solid var(--color-border)',
          }}
        >
          <FileText size={13} style={{ color: 'var(--color-text-muted)' }} />
          <span className="text-xs font-semibold text-text-muted uppercase tracking-widest">
            PDF Preview
          </span>
        </div>
        {/* flex-1 min-h-0 is critical — without min-h-0 the iframe never gets a bounded height */}
        <div className="flex-1 min-h-0" style={{ overflow: 'hidden' }}>
          <PdfPreview reportId={reportId} />
        </div>
      </div>
    </div>
  )
}