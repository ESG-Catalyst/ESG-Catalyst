import { useEffect, useRef, useState } from 'react'
import { animate, useInView } from 'framer-motion'

interface GaugeRingProps {
  score: number
  color: string
  label: string
  size: number
  animatedScore: number
}

function GaugeRing({ score, color, label, size, animatedScore }: GaugeRingProps) {
  const r = (size / 2) * 0.72
  const circumference = 2 * Math.PI * r
  const cx = size / 2
  const cy = size / 2
  const dash = Math.min(Math.max(animatedScore / 100, 0), 1) * circumference

  return (
    <div className="flex flex-col items-center gap-1">
      <svg
        width={size}
        height={size}
        style={{ transform: 'rotate(-90deg)' }}
        aria-label={`${label} score: ${Math.round(animatedScore)}`}
      >
        <circle
          cx={cx} cy={cy} r={r}
          fill="none"
          stroke="var(--color-border-subtle)"
          strokeWidth={size * 0.075}
        />
        <circle
          cx={cx} cy={cy} r={r}
          fill="none"
          stroke={color}
          strokeWidth={size * 0.075}
          strokeDasharray={`${dash} ${circumference - dash}`}
          strokeLinecap="round"
          style={{ transition: 'stroke-dasharray 0.05s linear' }}
        />
        <text
          x={cx} y={cy}
          textAnchor="middle"
          dominantBaseline="central"
          fill="var(--color-text)"
          fontSize={size * 0.24}
          fontWeight="600"
          fontFamily="var(--font-mono)"
          style={{ transform: 'rotate(90deg)', transformOrigin: `${cx}px ${cy}px` }}
        >
          {Math.round(animatedScore)}
        </text>
      </svg>
      <span className="text-xs font-medium" style={{ color }}>{label}</span>
    </div>
  )
}

interface ScoreGaugeProps {
  /** E/S/G scores 0–100 */
  scores?: { E: number; S: number; G: number }
  /** Overall composite score 0–100 */
  overall?: number
  size?: 'sm' | 'md' | 'lg'
}

const SIZE_MAP = { sm: 72, md: 96, lg: 120 }
const OVERALL_SIZE_MAP = { sm: 100, md: 128, lg: 160 }

const PILLAR_COLORS = {
  E: '#10B981',
  S: '#38BDF8',
  G: '#A78BFA',
}

export default function ScoreGauge({
  scores = { E: 72, S: 58, G: 65 },
  overall = 66,
  size = 'lg',
}: ScoreGaugeProps) {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-60px' })

  const [animE, setAnimE] = useState(0)
  const [animS, setAnimS] = useState(0)
  const [animG, setAnimG] = useState(0)
  const [animOverall, setAnimOverall] = useState(0)

  useEffect(() => {
    if (!inView) return
    const duration = 1.4
    const controls = [
      animate(0, scores.E, { duration, ease: 'easeOut', onUpdate: setAnimE }),
      animate(0, scores.S, { duration: duration * 0.9, ease: 'easeOut', delay: 0.1, onUpdate: setAnimS }),
      animate(0, scores.G, { duration: duration * 0.8, ease: 'easeOut', delay: 0.2, onUpdate: setAnimG }),
      animate(0, overall, { duration, ease: 'easeOut', onUpdate: setAnimOverall }),
    ]
    return () => controls.forEach((c) => c.stop())
  }, [inView, scores.E, scores.S, scores.G, overall])

  const ringSize = SIZE_MAP[size]
  const overallSize = OVERALL_SIZE_MAP[size]

  return (
    <div ref={ref} className="flex flex-col items-center gap-6">
      {/* Overall composite ring */}
      <div className="flex flex-col items-center gap-1">
        <GaugeRing
          score={overall}
          animatedScore={animOverall}
          color="var(--color-primary)"
          label="Overall"
          size={overallSize}
        />
      </div>
      {/* E / S / G pillar rings */}
      <div className="flex items-end gap-5">
        {(['E', 'S', 'G'] as const).map((pillar) => (
          <GaugeRing
            key={pillar}
            score={scores[pillar]}
            animatedScore={pillar === 'E' ? animE : pillar === 'S' ? animS : animG}
            color={PILLAR_COLORS[pillar]}
            label={pillar === 'E' ? 'Environmental' : pillar === 'S' ? 'Social' : 'Governance'}
            size={ringSize}
          />
        ))}
      </div>
    </div>
  )
}
