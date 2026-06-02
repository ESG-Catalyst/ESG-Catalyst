import { useState, type FormEvent } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import {
  Building2,
  Plus,
  X,
  ChevronDown,
  Download,
  Clock,
  CheckCircle2,
  FileText,
  AlertCircle,
  BarChart2,
  Users,
  Search,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import ScoreGauge from '@/components/ui/ScoreGauge'
import { useConsultantStore } from '@/store/consultant'
import { useAuthStore } from '@/store/auth'
import { cn } from '@/lib/utils'

// ─── Types ────────────────────────────────────────────────────────────────────

type InstitutionType = 'Commercial Bank' | 'NBFI' | 'Insurance'
type ReportStatus = 'DRAFT' | 'Pending review' | 'Report locked'

interface ClientInstitution {
  id: string
  name: string
  type: InstitutionType
  scores: { E: number; S: number; G: number; overall: number }
  lastActivity: string
  reportStatus: ReportStatus
  latestReportId: string | null
  griCoverage: number
  fraCoverage: number
  missingIndicators: number
  tier: string
}

interface ActivityItem {
  institutionId: string
  institutionName: string
  action: string
  time: string
  icon: React.ElementType
  iconColor: string
}

// ─── Mock data ────────────────────────────────────────────────────────────────

const MOCK_CLIENTS: ClientInstitution[] = [
  {
    id: 'c1',
    name: 'ADCB Egypt',
    type: 'Commercial Bank',
    scores: { E: 68, S: 72, G: 81, overall: 74 },
    lastActivity: '3 days ago',
    reportStatus: 'DRAFT',
    latestReportId: 'r-adcb-001',
    griCoverage: 62,
    fraCoverage: 100,
    missingIndicators: 9,
    tier: 'Established',
  },
  {
    id: 'c2',
    name: 'Beltone Financial',
    type: 'NBFI',
    scores: { E: 45, S: 61, G: 58, overall: 55 },
    lastActivity: '1 day ago',
    reportStatus: 'Pending review',
    latestReportId: 'r-beltone-002',
    griCoverage: 38,
    fraCoverage: 100,
    missingIndicators: 17,
    tier: 'Established',
  },
  {
    id: 'c3',
    name: 'ADIB Egypt',
    type: 'Commercial Bank',
    scores: { E: 28, S: 34, G: 41, overall: 34 },
    lastActivity: '5 days ago',
    reportStatus: 'DRAFT',
    latestReportId: null,
    griCoverage: 21,
    fraCoverage: 0,
    missingIndicators: 31,
    tier: 'Laggard',
  },
  {
    id: 'c4',
    name: 'EFG Hermes',
    type: 'NBFI',
    scores: { E: 83, S: 79, G: 88, overall: 83 },
    lastActivity: '12 hours ago',
    reportStatus: 'Report locked',
    latestReportId: 'r-efg-004',
    griCoverage: 79,
    fraCoverage: 100,
    missingIndicators: 5,
    tier: 'Leading',
  },
]

const MOCK_ACTIVITY: ActivityItem[] = [
  {
    institutionId: 'c4',
    institutionName: 'EFG Hermes',
    action: 'Report approved and locked',
    time: '12h ago',
    icon: CheckCircle2,
    iconColor: '#10B981',
  },
  {
    institutionId: 'c2',
    institutionName: 'Beltone Financial',
    action: 'Pipeline completed — 8 metrics extracted',
    time: '1d ago',
    icon: BarChart2,
    iconColor: '#0D9488',
  },
  {
    institutionId: 'c2',
    institutionName: 'Beltone Financial',
    action: 'ESG report uploaded for processing',
    time: '1d ago',
    icon: FileText,
    iconColor: '#38BDF8',
  },
  {
    institutionId: 'c1',
    institutionName: 'ADCB Egypt',
    action: '3 metrics approved by reviewer',
    time: '3d ago',
    icon: CheckCircle2,
    iconColor: '#10B981',
  },
  {
    institutionId: 'c3',
    institutionName: 'ADIB Egypt',
    action: '31 indicators still missing disclosure',
    time: '5d ago',
    icon: AlertCircle,
    iconColor: '#F59E0B',
  },
]

// ─── Helpers ──────────────────────────────────────────────────────────────────

function TIER_COLOR(tier: string): string {
  if (tier === 'Leading') return '#10B981'
  if (tier === 'Established') return '#0D9488'
  if (tier === 'Developing') return '#F59E0B'
  return '#EF4444'
}

function TYPE_BADGE_STYLE(type: InstitutionType): React.CSSProperties {
  const map: Record<InstitutionType, { bg: string; color: string }> = {
    'Commercial Bank': { bg: '#38BDF820', color: '#38BDF8' },
    NBFI: { bg: '#A78BFA20', color: '#A78BFA' },
    Insurance: { bg: '#F59E0B20', color: '#F59E0B' },
  }
  const s = map[type]
  return { background: s.bg, color: s.color, border: `1px solid ${s.color}40` }
}

function REPORT_STATUS_STYLE(status: ReportStatus): React.CSSProperties {
  if (status === 'Report locked')
    return { background: '#A78BFA20', color: '#A78BFA', border: '1px solid #A78BFA40' }
  if (status === 'Pending review')
    return { background: '#F59E0B20', color: '#F59E0B', border: '1px solid #F59E0B40' }
  return { background: '#6B728020', color: '#9CA3AF', border: '1px solid #6B728040' }
}

// ─── Shared Card ──────────────────────────────────────────────────────────────

function Card({
  children,
  className = '',
  style = {},
}: {
  children: React.ReactNode
  className?: string
  style?: React.CSSProperties
}) {
  return (
    <div
      className={cn('rounded-xl bg-surface border border-border', className)}
      style={style}
    >
      {children}
    </div>
  )
}

// ─── Add Client Modal ─────────────────────────────────────────────────────────

function AddClientModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [type, setType] = useState<InstitutionType>('Commercial Bank')
  const [submitted, setSubmitted] = useState(false)

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!name.trim() || !email.trim()) return
    setSubmitted(true)
    setTimeout(onClose, 1400)
  }

  const inputCls = cn(
    'w-full rounded-lg px-3 py-2.5 text-sm outline-none transition-colors',
    'bg-surface-raised border border-border-subtle hover:border-border',
    'focus-visible:ring-2 focus-visible:ring-primary focus-visible:border-primary',
    'text-text placeholder:text-text-subtle',
  )

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(3px)' }}
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 8 }}
        transition={{ duration: 0.2 }}
        className="rounded-2xl p-6 w-full max-w-md mx-4 shadow-2xl bg-surface border border-border"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-base font-semibold text-text">Add Client Institution</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="text-text-muted hover:text-text transition-colors rounded-lg p-1.5 hover:bg-surface-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <X size={15} aria-hidden="true" />
          </button>
        </div>

        {submitted ? (
          <div className="py-8 flex flex-col items-center gap-3 text-center">
            <div className="w-12 h-12 rounded-full bg-success/15 flex items-center justify-center">
              <CheckCircle2 size={24} style={{ color: '#10B981' }} aria-hidden="true" />
            </div>
            <p className="text-sm font-semibold text-text">Invitation sent</p>
            <p className="text-xs text-text-muted">
              {name} will receive an onboarding email at{' '}
              <span className="text-text">{email}</span>.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-text-muted">Institution name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Cairo International Bank"
                className={inputCls}
                autoFocus
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-text-muted">Institution type</label>
              <select
                value={type}
                onChange={(e) => setType(e.target.value as InstitutionType)}
                className={cn(inputCls, 'appearance-none')}
              >
                <option>Commercial Bank</option>
                <option>NBFI</option>
                <option>Insurance</option>
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-text-muted">Contact email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="sustainability@bank.eg"
                className={inputCls}
              />
            </div>
            <div className="flex gap-3 mt-2">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 py-2.5 rounded-lg text-sm font-medium transition-colors bg-surface-raised text-text-muted hover:text-text hover:bg-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!name.trim() || !email.trim()}
                className="flex-1 py-2.5 rounded-lg text-sm font-semibold transition-all disabled:opacity-40 disabled:cursor-not-allowed bg-primary hover:bg-primary-hover text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                Send Invitation
              </button>
            </div>
          </form>
        )}
      </motion.div>
    </div>
  )
}

// ─── Pillar bars ──────────────────────────────────────────────────────────────

function PillarBar({ label, score, color }: { label: string; score: number; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-bold w-3 shrink-0" style={{ color }}>
        {label}
      </span>
      <div className="flex-1 rounded-full overflow-hidden h-1.5 bg-border-subtle">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${score}%`, background: color }}
        />
      </div>
      <span
        className="text-xs tabular-nums w-7 text-end shrink-0 text-text-muted"
        style={{ fontFamily: 'var(--font-mono)' }}
      >
        {score}
      </span>
    </div>
  )
}

// ─── Client Card ──────────────────────────────────────────────────────────────

function ClientCard({ client }: { client: ClientInstitution }) {
  const navigate = useNavigate()
  const setActiveClient = useConsultantStore((s) => s.setActiveClient)

  function openDashboard() {
    setActiveClient({
      companyId: client.id,
      companyName: client.name,
      institutionType: client.type,
    })
    navigate('/dashboard')
  }

  const tierColor = TIER_COLOR(client.tier)

  return (
    <motion.div
      whileHover={{ y: -2 }}
      transition={{ duration: 0.15 }}
    >
      <Card className="p-5 flex flex-col gap-4 hover:border-primary transition-colors cursor-default">
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-text truncate">{client.name}</h3>
            <span
              className="inline-flex items-center mt-1 px-2 py-0.5 rounded-full text-xs font-medium"
              style={TYPE_BADGE_STYLE(client.type)}
            >
              {client.type}
            </span>
          </div>
          <div className="shrink-0 w-12 h-12 flex items-center justify-center rounded-xl bg-surface-raised">
            <Building2 size={20} style={{ color: 'var(--color-primary)' }} aria-hidden="true" />
          </div>
        </div>

        {/* Score gauge + pillar bars */}
        <div className="flex items-center gap-4">
          <div className="shrink-0">
            <ScoreGauge scores={client.scores} overall={client.scores.overall} size="sm" />
          </div>
          <div className="flex-1 flex flex-col gap-2">
            <PillarBar label="E" score={client.scores.E} color="#10B981" />
            <PillarBar label="S" score={client.scores.S} color="#38BDF8" />
            <PillarBar label="G" score={client.scores.G} color="#A78BFA" />
          </div>
        </div>

        {/* Meta row */}
        <div className="flex items-center justify-between text-xs border-t border-border-subtle pt-3">
          <span className="flex items-center gap-1 text-text-muted">
            <Clock size={10} aria-hidden="true" />
            Updated {client.lastActivity}
          </span>
          <span
            className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium"
            style={REPORT_STATUS_STYLE(client.reportStatus)}
          >
            {client.reportStatus}
          </span>
        </div>

        {/* Tier + coverage summary */}
        <div className="flex items-center gap-2">
          <span
            className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border"
            style={{
              background: `${tierColor}18`,
              color: tierColor,
              borderColor: `${tierColor}35`,
            }}
          >
            {client.tier}
          </span>
          <span className="text-xs text-text-subtle">
            {client.griCoverage}% GRI · {client.missingIndicators} missing
          </span>
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          <button
            onClick={openDashboard}
            className="flex-1 py-2 rounded-lg text-xs font-semibold transition-all bg-primary hover:bg-primary-hover text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            Open Dashboard
          </button>
          {client.latestReportId ? (
            <Link
              to={`/report/${client.latestReportId}`}
              className="flex-1 py-2 rounded-lg text-xs font-semibold text-center transition-all bg-surface-raised text-text-muted hover:bg-border hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              View Report
            </Link>
          ) : (
            <button
              disabled
              className="flex-1 py-2 rounded-lg text-xs font-semibold opacity-40 cursor-not-allowed bg-surface-raised text-text-muted"
            >
              No Report Yet
            </button>
          )}
        </div>
      </Card>
    </motion.div>
  )
}

// ─── Comparison panel ─────────────────────────────────────────────────────────

const COMPARE_ROWS = [
  { key: 'overall', label: 'Overall Score' },
  { key: 'E', label: 'E Score' },
  { key: 'S', label: 'S Score' },
  { key: 'G', label: 'G Score' },
  { key: 'griCoverage', label: 'GRI Coverage %' },
  { key: 'fraCoverage', label: 'FRA Coverage %' },
  { key: 'missingIndicators', label: 'Missing Indicators', lowerIsBetter: true },
  { key: 'tier', label: 'Tier', isText: true },
] as const

type RowKey = (typeof COMPARE_ROWS)[number]['key']

function getCellValue(client: ClientInstitution, key: RowKey): number | string {
  if (key === 'overall') return client.scores.overall
  if (key === 'E') return client.scores.E
  if (key === 'S') return client.scores.S
  if (key === 'G') return client.scores.G
  if (key === 'griCoverage') return client.griCoverage
  if (key === 'fraCoverage') return client.fraCoverage
  if (key === 'missingIndicators') return client.missingIndicators
  return client.tier
}

function downloadComparisonCSV(clients: ClientInstitution[]) {
  const headers = ['Metric', ...clients.map((c) => c.name)]
  const rows = COMPARE_ROWS.map((row) => [
    row.label,
    ...clients.map((c) => String(getCellValue(c, row.key))),
  ])
  const csv = [headers, ...rows].map((r) => r.join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'esg-comparison.csv'
  a.click()
  URL.revokeObjectURL(url)
}

function ComparisonPanel({ clients }: { clients: ClientInstitution[] }) {
  const [selected, setSelected] = useState<string[]>([])
  const [dropdownOpen, setDropdownOpen] = useState(false)

  const toggleClient = (id: string) => {
    setSelected((prev) =>
      prev.includes(id)
        ? prev.filter((x) => x !== id)
        : prev.length < 4
          ? [...prev, id]
          : prev,
    )
  }

  const comparedClients = clients.filter((c) => selected.includes(c.id))

  function getBestValue(key: RowKey, lowerIsBetter = false): number | string {
    const vals = comparedClients
      .map((c) => getCellValue(c, key))
      .filter((v) => typeof v === 'number') as number[]
    if (vals.length === 0) return ''
    return lowerIsBetter ? Math.min(...vals) : Math.max(...vals)
  }

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="text-sm font-semibold text-text">Side-by-side comparison</h2>
          <p className="text-xs text-text-muted mt-0.5">Select 2–4 institutions to compare</p>
        </div>
        {comparedClients.length >= 2 && (
          <button
            onClick={() => downloadComparisonCSV(comparedClients)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors bg-surface-raised text-text-muted border border-border hover:text-text hover:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <Download size={12} aria-hidden="true" />
            Export CSV
          </button>
        )}
      </div>

      {/* Multi-select dropdown */}
      <div className="relative mb-5">
        <button
          onClick={() => setDropdownOpen((v) => !v)}
          aria-haspopup="listbox"
          aria-expanded={dropdownOpen}
          className="w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-sm transition-colors bg-surface-raised border border-border-subtle hover:border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          style={{ color: selected.length ? 'var(--color-text)' : 'var(--color-text-subtle)' }}
        >
          <span className="truncate">
            {selected.length === 0
              ? 'Choose institutions…'
              : clients
                  .filter((c) => selected.includes(c.id))
                  .map((c) => c.name)
                  .join(', ')}
          </span>
          <ChevronDown
            size={14}
            className={cn('shrink-0 ms-2 transition-transform', dropdownOpen && 'rotate-180')}
            aria-hidden="true"
          />
        </button>

        <AnimatePresence>
          {dropdownOpen && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.12 }}
              className="absolute z-20 top-full start-0 end-0 mt-1 rounded-xl py-1 shadow-lg overflow-hidden bg-surface border border-border"
              role="listbox"
              aria-multiselectable="true"
            >
              {clients.map((c) => {
                const checked = selected.includes(c.id)
                const disabled = !checked && selected.length >= 4
                return (
                  <button
                    key={c.id}
                    role="option"
                    aria-selected={checked}
                    onClick={() => !disabled && toggleClient(c.id)}
                    disabled={disabled}
                    className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-start transition-colors disabled:opacity-40 hover:bg-surface-raised text-text focus-visible:outline-none focus-visible:bg-surface-raised"
                  >
                    <div
                      className="w-4 h-4 rounded flex items-center justify-center shrink-0 transition-colors"
                      style={{
                        border: `2px solid ${checked ? 'var(--color-primary)' : 'var(--color-border)'}`,
                        background: checked ? 'var(--color-primary)' : 'transparent',
                      }}
                    >
                      {checked && (
                        <svg viewBox="0 0 8 8" width="8" height="8" fill="none" aria-hidden="true">
                          <path
                            d="M1.5 4L3 5.5L6.5 2"
                            stroke="#fff"
                            strokeWidth="1.5"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      )}
                    </div>
                    <span className="flex-1 text-sm">{c.name}</span>
                    <span className="text-xs text-text-muted">{c.type}</span>
                  </button>
                )
              })}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Comparison table */}
      {comparedClients.length < 2 ? (
        <div className="rounded-xl py-10 flex flex-col items-center gap-2 text-center bg-surface-raised">
          <BarChart2 size={24} className="text-text-subtle opacity-50" aria-hidden="true" />
          <p className="text-sm text-text-muted">Select at least 2 institutions to compare</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-raised border-b border-border">
                <th
                  scope="col"
                  className="py-2.5 px-4 text-start text-xs font-semibold text-text-muted w-44"
                >
                  Metric
                </th>
                {comparedClients.map((c) => (
                  <th
                    key={c.id}
                    scope="col"
                    className="py-2.5 px-4 text-start text-xs font-semibold text-text whitespace-nowrap"
                  >
                    {c.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {COMPARE_ROWS.map((row, i) => {
                const lowerIsBetter = 'lowerIsBetter' in row ? row.lowerIsBetter : false
                const isText = 'isText' in row ? row.isText : false
                const best = isText ? null : getBestValue(row.key, lowerIsBetter)

                return (
                  <tr
                    key={row.key}
                    className={cn(
                      'border-b border-border',
                      i % 2 === 0 ? 'bg-surface' : 'bg-surface-raised/50',
                    )}
                  >
                    <td className="py-2.5 px-4 text-xs font-medium text-text-muted whitespace-nowrap">
                      {row.label}
                    </td>
                    {comparedClients.map((c) => {
                      const val = getCellValue(c, row.key)
                      const isBest = !isText && val === best
                      return (
                        <td
                          key={c.id}
                          className="py-2.5 px-4 text-xs font-medium tabular-nums"
                          style={{
                            background: isBest ? '#10B98112' : undefined,
                            color: isBest
                              ? '#10B981'
                              : isText
                              ? TIER_COLOR(val as string)
                              : 'var(--color-text)',
                            fontFamily: isText ? undefined : 'var(--font-mono)',
                          }}
                        >
                          {isText
                            ? val
                            : typeof val === 'number' && row.key !== 'missingIndicators'
                            ? `${val}${['griCoverage', 'fraCoverage'].includes(row.key) ? '%' : ''}`
                            : val}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

// ─── Activity feed ────────────────────────────────────────────────────────────

function ActivityFeed({ items }: { items: ActivityItem[] }) {
  const navigate = useNavigate()
  const setActiveClient = useConsultantStore((s) => s.setActiveClient)
  const clients = MOCK_CLIENTS

  return (
    <Card className="p-5 flex flex-col gap-3" style={{ height: 'fit-content' }}>
      <p className="text-[10px] font-bold uppercase tracking-widest text-text-muted mb-1">
        Client Activity
      </p>
      <ul className="flex flex-col gap-3" role="list">
        {items.map((item, i) => {
          const client = clients.find((c) => c.id === item.institutionId)
          return (
            <li key={i} className="flex items-start gap-3">
              <div
                className="w-7 h-7 rounded-lg shrink-0 flex items-center justify-center text-xs font-bold"
                style={{ background: `${item.iconColor}18`, color: item.iconColor }}
                aria-hidden="true"
              >
                {item.institutionName.slice(0, 2).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <button
                  onClick={() => {
                    if (client) {
                      setActiveClient({
                        companyId: client.id,
                        companyName: client.name,
                        institutionType: client.type,
                      })
                      navigate('/dashboard')
                    }
                  }}
                  className="text-xs font-semibold hover:underline text-start text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded"
                >
                  {item.institutionName}
                </button>
                <p className="text-xs text-text-muted leading-snug mt-0.5">{item.action}</p>
              </div>
              <span className="text-xs text-text-subtle shrink-0 flex items-center gap-1 mt-0.5">
                <Clock size={10} aria-hidden="true" />
                {item.time}
              </span>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}

// ─── Access denied ────────────────────────────────────────────────────────────

function AccessDenied() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="w-14 h-14 rounded-2xl bg-danger/10 flex items-center justify-center mb-5 border border-danger/20">
        <Users size={24} style={{ color: '#EF4444' }} aria-hidden="true" />
      </div>
      <p className="text-base font-semibold text-text mb-2">Access restricted</p>
      <p className="text-sm text-text-muted mb-6 max-w-sm leading-relaxed">
        The Consultant Workspace is only available to consultant and admin accounts.
      </p>
      <Link
        to="/dashboard"
        className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-semibold rounded-lg transition-all bg-primary hover:bg-primary-hover text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        Back to Dashboard
      </Link>
    </div>
  )
}

// ─── ConsultantWorkspace ──────────────────────────────────────────────────────

export default function ConsultantWorkspace() {
  const [showAddModal, setShowAddModal] = useState(false)
  const [search, setSearch] = useState('')
  const role = useAuthStore((s) => s.role)

  if (role !== 'consultant' && role !== 'admin') {
    return (
      <div className="p-6 max-w-[1400px] mx-auto">
        <AccessDenied />
      </div>
    )
  }

  const filteredClients = search.trim()
    ? MOCK_CLIENTS.filter((c) =>
        c.name.toLowerCase().includes(search.toLowerCase()) ||
        c.type.toLowerCase().includes(search.toLowerCase()),
      )
    : MOCK_CLIENTS

  return (
    <div className="p-6 max-w-[1400px] mx-auto">
      {/* Page header */}
      <div className="flex items-start justify-between mb-6 gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-text leading-tight">
            Consultant Workspace
          </h1>
          <p className="text-sm text-text-muted mt-1">
            Manage and compare your client portfolio.
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0 flex-wrap">
          {/* Portfolio count chip */}
          <span className="text-xs text-text-muted bg-surface-raised px-3 py-1.5 rounded-full border border-border">
            Managing {MOCK_CLIENTS.length} institutions
          </span>
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all bg-primary hover:bg-primary-hover text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <Plus size={15} aria-hidden="true" />
            Add Client
          </button>
        </div>
      </div>

      {/* Search bar */}
      <div className="mb-5">
        <div className="relative max-w-sm">
          <Search
            size={14}
            className="absolute start-3 top-1/2 -translate-y-1/2 text-text-muted"
            aria-hidden="true"
          />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search institutions…"
            aria-label="Search client institutions"
            className="w-full ps-9 pe-4 py-2 text-sm rounded-lg bg-surface border border-border-subtle hover:border-border text-text placeholder:text-text-subtle outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:border-primary transition-colors"
          />
        </div>
      </div>

      {/* Main layout: portfolio grid + activity feed */}
      <div className="flex gap-6">
        {/* Left: client grid + comparison */}
        <div className="flex-1 min-w-0 flex flex-col gap-6">
          {/* Client portfolio grid */}
          {filteredClients.length === 0 ? (
            <div className="rounded-xl border border-border bg-surface-raised py-12 flex flex-col items-center gap-2 text-center">
              <Building2 size={24} className="text-text-subtle opacity-40" aria-hidden="true" />
              <p className="text-sm text-text-muted">No institutions match your search.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {filteredClients.map((client) => (
                <ClientCard key={client.id} client={client} />
              ))}
            </div>
          )}

          {/* Comparison panel */}
          <ComparisonPanel clients={MOCK_CLIENTS} />
        </div>

        {/* Right: activity feed */}
        <div className="w-[280px] shrink-0 hidden lg:block">
          <ActivityFeed items={MOCK_ACTIVITY} />
        </div>
      </div>

      {/* Add client modal */}
      <AnimatePresence>
        {showAddModal && <AddClientModal onClose={() => setShowAddModal(false)} />}
      </AnimatePresence>
    </div>
  )
}
