import { useEffect, useRef, useState } from 'react'
import { animate, useInView } from 'framer-motion'
import { cn } from '@/lib/utils'
import { tierKeyFor, tierColorFor, TIER_LABELS_EN } from '@/lib/score'

/* ── Score tier helper ──────────────────────────────────────────────────────
 * Derives the badge from the shared banding (lib/score.ts) so this component
 * never diverges from the page-level tier chips or the generated PDF. Labels
 * are the English fallbacks; i18n-aware pages pass showTier={false} and render
 * their own translated chip instead. */
function scoreTier(score: number): { label: string; color: string } {
  return { label: TIER_LABELS_EN[tierKeyFor(score)], color: tierColorFor(score) }
}

/* ── Pillar colour map — uses CSS vars so they flip with theme ─────────── */
const PILLAR_COLORS: Record<string, string> = {
  E: 'var(--color-success)',
  S: 'var(--color-info)',
  G: '#A78BFA',   /* violet — not a semantic token but consistent across themes */
}
const PILLAR_LABELS: Record<string, string> = {
  E: 'Environmental',
  S: 'Social',
  G: 'Governance',
}

/* ── GaugeRing ──────────────────────────────────────────────────────────── */
interface GaugeRingProps {
  score: number
  animatedScore: number
  color: string
  label: string
  size: number
  /** Show tier badge below the label */
  showTier?: boolean
}

function GaugeRing({ score, animatedScore, color, label, size, showTier }: GaugeRingProps) {
  const r            = (size / 2) * 0.72
  const strokeWidth  = Math.max(size * 0.075, 4)
  const circumference = 2 * Math.PI * r
  const cx = size / 2
  const cy = size / 2

  // Arc fills 270° (¾ of the circle) for a gauge feel rather than a full ring
  const gaugeFraction = 0.75
  const arcTotal  = circumference * gaugeFraction
  const dash      = Math.min(Math.max(animatedScore / 100, 0), 1) * arcTotal
  const tier       = showTier ? scoreTier(score) : null

  // Rotation: start arc at bottom-left (135° from top = 225° CSS)
  const startAngle = 135

  return (
    <div className="flex flex-col items-center gap-1.5">
      <div className="relative">
        <svg
          width={size}
          height={size}
          style={{ transform: `rotate(${startAngle}deg)` }}
          aria-label={`${label} score: ${Math.round(animatedScore)}`}
          role="img"
          focusable="false"
        >
          {/* Track */}
          <circle
            cx={cx} cy={cy} r={r}
            fill="none"
            stroke="var(--color-border-subtle)"
            strokeWidth={strokeWidth}
            strokeDasharray={`${arcTotal} ${circumference - arcTotal}`}
            strokeLinecap="round"
            opacity="0.7"
          />
          {/* Fill */}
          <circle
            cx={cx} cy={cy} r={r}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeDasharray={`${dash} ${circumference - dash}`}
            strokeLinecap="round"
            style={{ transition: 'stroke-dasharray 0.04s linear', filter: `drop-shadow(0 0 ${strokeWidth * 0.6}px ${color}60)` }}
          />
          {/* Score text */}
          <text
            x={cx} y={cy}
            textAnchor="middle"
            dominantBaseline="central"
            fill="var(--color-text)"
            fontSize={size * 0.24}
            fontWeight="700"
            fontFamily="var(--font-mono)"
            style={{ transform: `rotate(${-startAngle}deg)`, transformOrigin: `${cx}px ${cy}px` }}
          >
            {Math.round(animatedScore)}
          </text>
        </svg>
      </div>

      {/* Label */}
      <span
        className="text-xs font-semibold tracking-wide"
        style={{ color }}
      >
        {label}
      </span>

      {/* Tier badge */}
      {tier && (
        <span
          className={cn(
            'inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium border',
            'bg-surface-raised text-text-muted border-border',
          )}
        >
          {tier.label}
        </span>
      )}
    </div>
  )
}

/* ── ScoreGauge (exported) ──────────────────────────────────────────────── */
const SIZE_MAP         = { sm: 72,  md: 96,  lg: 120 } as const
const OVERALL_SIZE_MAP = { sm: 100, md: 128, lg: 160 } as const

interface ScoreGaugeProps {
  /** E/S/G scores 0–100 */
  scores?: { E: number; S: number; G: number }
  /** Overall composite score 0–100 */
  overall?: number
  size?: 'sm' | 'md' | 'lg'
  /** Show tier label below overall ring */
  showTier?: boolean
}

export default function ScoreGauge({
  scores = { E: 72, S: 58, G: 65 },
  overall = 66,
  size = 'lg',
  showTier = true,
}: ScoreGaugeProps) {
  const ref    = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-60px' })

  const [animE,       setAnimE]       = useState(0)
  const [animS,       setAnimS]       = useState(0)
  const [animG,       setAnimG]       = useState(0)
  const [animOverall, setAnimOverall] = useState(0)

  useEffect(() => {
    if (!inView) return
    const dur = 1.4
    const controls = [
      animate(0, scores.E,  { duration: dur,        ease: 'easeOut',             onUpdate: setAnimE }),
      animate(0, scores.S,  { duration: dur * 0.9,  ease: 'easeOut', delay: 0.1, onUpdate: setAnimS }),
      animate(0, scores.G,  { duration: dur * 0.8,  ease: 'easeOut', delay: 0.2, onUpdate: setAnimG }),
      animate(0, overall,   { duration: dur,        ease: 'easeOut',             onUpdate: setAnimOverall }),
    ]
    return () => controls.forEach((c) => c.stop())
  }, [inView, scores.E, scores.S, scores.G, overall])

  const ringSize    = SIZE_MAP[size]
  const overallSize = OVERALL_SIZE_MAP[size]

  return (
    <div
      ref={ref}
      className="flex flex-col items-center gap-8"
      aria-label={`ESG scores — Overall: ${overall}, Environmental: ${scores.E}, Social: ${scores.S}, Governance: ${scores.G}`}
    >
      {/* Overall */}
      <GaugeRing
        score={overall}
        animatedScore={animOverall}
        color="var(--color-primary)"
        label="Overall"
        size={overallSize}
        showTier={showTier}
      />

      {/* Divider with pillar scores label */}
      <div className="flex items-center gap-3 w-full">
        <div className="flex-1 h-px bg-border" />
        <span className="text-xs text-text-subtle whitespace-nowrap">Pillar Breakdown</span>
        <div className="flex-1 h-px bg-border" />
      </div>

      {/* E / S / G */}
      <div className="flex items-start gap-6 flex-wrap justify-center">
        {(['E', 'S', 'G'] as const).map((pillar) => (
          <GaugeRing
            key={pillar}
            score={scores[pillar]}
            animatedScore={pillar === 'E' ? animE : pillar === 'S' ? animS : animG}
            color={PILLAR_COLORS[pillar]}
            label={PILLAR_LABELS[pillar]}
            size={ringSize}
          />
        ))}
      </div>
    </div>
  )
}
