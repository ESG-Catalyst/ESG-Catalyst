// Single source of truth for ESG tier banding on the frontend.
//
// Bands, labels, and ordering mirror the backend scorer's `_benchmark_tier`
// (backend/app/core/scoring/scorer.py) EXACTLY, so the tier shown anywhere on
// the site is the same tier the generated PDF report prints for the same
// composite score. Do not fork these thresholds in individual components — the
// whole point is that every surface derives the tier identically.

export type TierKey =
  | 'leader'
  | 'aboveAverage'
  | 'average'
  | 'belowAverage'
  | 'laggard'

/**
 * Map a 0–100 composite ESG score to a tier key.
 * Mirrors backend `_benchmark_tier`: ≥85 Leader, ≥70 Above average,
 * ≥50 Average, ≥30 Below average, else Laggard.
 */
export function tierKeyFor(score: number): TierKey {
  if (score >= 85) return 'leader'
  if (score >= 70) return 'aboveAverage'
  if (score >= 50) return 'average'
  if (score >= 30) return 'belowAverage'
  return 'laggard'
}

/** Tier accent colours (hex so they read identically across themes). */
export const TIER_COLORS: Record<TierKey, string> = {
  leader: '#10B981',
  aboveAverage: '#0D9488',
  average: '#F59E0B',
  belowAverage: '#F97316',
  laggard: '#EF4444',
}

/**
 * English fallback labels — for non-i18n surfaces (e.g. the ScoreGauge badge).
 * i18n-aware pages should translate via `t('tier.' + tierKeyFor(score))`.
 */
export const TIER_LABELS_EN: Record<TierKey, string> = {
  leader: 'Leader',
  aboveAverage: 'Above average',
  average: 'Average',
  belowAverage: 'Below average',
  laggard: 'Laggard',
}

export function tierColorFor(score: number): string {
  return TIER_COLORS[tierKeyFor(score)]
}
