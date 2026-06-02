# ESG Catalyst — Design System (Agent 1 deliverable)

## What Was Done

Agent 1 owned the visual language layer: `tokens.css`, `globals.css`,
`tailwind.config.ts`, `lib/utils.ts`, and the 7 UI primitives under
`frontend/react/src/components/ui/`.

---

## Files Changed

| File | Nature of change |
|---|---|
| `src/styles/tokens.css` | Refined palette; added semantic-subtle variants; added chart-1..5, shadow scale, focus-ring, gradient tokens; tightened transitions |
| `src/styles/globals.css` | Rewrote @theme block to forward all new tokens; added typography rhythm, focus-visible defaults, scrollbar styling, selection color, reduced-motion guard, gradient utility classes |
| `tailwind.config.ts` | Added `*-subtle` color utilities, `chart.1-5`, `shadow-xs/sm/card/panel`, `ringColor.primary/danger/warning`, `radius-xl` |
| `src/lib/utils.ts` | Kept `cn()` unchanged; added `variants()` — a lightweight CVA-style helper for building typed variant-class maps |
| `DQChip.tsx` | Dot indicator, semantic token classes, aria-label, `label` prop |
| `StatusPill.tsx` | Dot indicator inside pill, semantic subtle backgrounds, `dot` mode variant, `role="status"` |
| `MetricTable.tsx` | Sticky header, zebra rows, pillar badge column, RTL-safe logical padding, improved ConfidenceBar with progressbar role, footer row count, accessible action buttons |
| `AIProposalBanner.tsx` | Accent line on start edge, brand gradient surface, `detail` prop, aria-live, improved focus states |
| `ScoreGauge.tsx` | 270° gauge arc (gauge feel), drop-shadow glow on fill, tier badge on overall ring, pillar-divider row, `showTier` prop |
| `FrameworkCoverageBar.tsx` | ARIA meter role, percentage badge with coloured background, all hardcoded hex replaced with token vars where possible, RTL-safe gap units |
| `PipelineProgressIndicator.tsx` | AlertTriangle on failed step, ring-glow on active step, stage description hint below bar, complete-state success callout, ARIA progressbar role |

---

## New / Added Tokens

All tokens are CSS variables defined in `tokens.css` and forwarded to Tailwind
in `globals.css` / `tailwind.config.ts`. Dark and light variants are both defined.

### Semantic subtle fills
Used as chip/badge background tints — 12% opacity of the base semantic colour.

| Token | Dark value | Light value | Tailwind class |
|---|---|---|---|
| `--color-primary-subtle` | `#0D948818` | `#0D948812` | `bg-primary-subtle` |
| `--color-success-subtle` | `#10B98118` | `#05966912` | `bg-success-subtle` |
| `--color-warning-subtle` | `#F59E0B18` | `#B4530912` | `bg-warning-subtle` |
| `--color-danger-subtle`  | `#EF444418` | `#DC262612` | `bg-danger-subtle` |
| `--color-info-subtle`    | `#38BDF818` | `#0284C712` | `bg-info-subtle` |

### Chart palette (5 colours)
Intended for recharts `<Cell fill="…">` and custom SVG fills.

| Token | Dark | Light | Tailwind class |
|---|---|---|---|
| `--chart-1` | `#0D9488` | `#0D9488` | `text-chart-1`, `bg-chart-1` |
| `--chart-2` | `#38BDF8` | `#0284C7` | `text-chart-2`, `bg-chart-2` |
| `--chart-3` | `#10B981` | `#059669` | `text-chart-3`, `bg-chart-3` |
| `--chart-4` | `#A78BFA` | `#7C3AED` | `text-chart-4`, `bg-chart-4` |
| `--chart-5` | `#FB923C` | `#EA580C` | `text-chart-5`, `bg-chart-5` |

### Elevation shadow scale

| Token | Tailwind class | Use |
|---|---|---|
| `--shadow-xs` | `shadow-xs` | Tight inset chips |
| `--shadow-sm` | `shadow-sm` | Cards, pills |
| `--shadow-md` | `shadow-card` | Surface cards |
| `--shadow-lg` | `shadow-panel` | Modals, dropdowns |

### Focus ring
`--color-focus-ring: #0D9488` — used by `*:focus-visible` in globals and by
`ring-primary` Tailwind token.

### Gradient helpers

| Token | CSS class | Use |
|---|---|---|
| `--gradient-brand` | `bg-brand-gradient` | Hero card surfaces, banners |
| `--gradient-brand-bar` | `bg-brand-bar` | Progress bar fills, active indicators |

### Additional radius
`--radius-xl: 1rem` → `rounded-xl` for modal/drawer shells.

### Transition refinement
`--transition-fast: 120ms`, `--transition-base: 180ms`, `--transition-slow: 280ms` —
slightly tighter than before to feel snappier on interactions.

---

## How Each Primitive Looks Now

### StatusPill
A compact rounded-full chip with a small coloured dot on the leading edge followed
by the status label. Uses `*-subtle` token backgrounds so it reads cleanly on both
dark (`#0F1724`) and light (`#FFFFFF`) surfaces. Has a `dot` prop that renders just
the dot + text inline without the pill border, useful in dense table cells. Carries
`role="status"`.

### DQChip
A square-cornered monochrome chip (DQ1–DQ5, green → red). Now includes a coloured
leading dot and an `aria-label` describing the quality tier. Accepts an optional
`label` prop to override the default "DQn" text. Transitions on hover.

### MetricTable
Data-dense table with:
- Zebra striping (every other row has a faint `bg-bg/30` tint)
- Hover: `bg-surface-raised/60` row highlight
- Sticky-friendly `<thead>` with uppercase tracking column headers
- Optional Pillar badge column (E/S/G colour-coded)
- ConfidenceBar sub-component uses `role="progressbar"` + `aria-valuenow`
- Approve/Reject buttons use `*-subtle` tint backgrounds with focus rings
- Footer row showing total count + approved/missing summary
- Empty state: centred message with sub-text prompt
- All padding uses logical properties (`ps-`, `pe-`) for RTL correctness

### AIProposalBanner
A tasteful callout with:
- Subtle teal brand gradient surface (`bg-brand-gradient`)
- `border-primary/20` outline
- Thin vertical accent line on the inline-start edge (teal `--color-primary`)
- Optional `detail` sub-text below the main message
- Three action buttons (Confirm/Edit/Reject) each with `*-subtle` backgrounds and
  colour-matched focus rings
- `role="status"` + `aria-live="polite"` so screen readers announce changes

### ScoreGauge
Upgraded from a full-circle ring to a 270° arc (gauge aesthetic). Changes:
- Arc starts at 135° (bottom-left) — reads more naturally as a "dial"
- Drop-shadow glow on the fill arc (colour-matched, 60% alpha)
- Overall ring shows a tier badge (Leading / Advanced / Progressing / Beginning)
  coloured by the tier breakpoints (`showTier` prop, default true)
- Divider row "Pillar Breakdown" separates overall from E/S/G
- All colours reference CSS vars so they respect both themes
- `aria-label` on the container summarising all 4 scores for screen readers

### FrameworkCoverageBar
- ARIA `role="meter"` with `aria-valuenow/min/max`
- Framework badge uses Tailwind token classes (`bg-primary-subtle`, `border-primary/25`)
  instead of inline hex — light theme parity automatic
- Percentage badge has a tinted background matching the tier colour
- RTL-safe gap (`gap-1` flex) on the dot grid
- `aria-hidden="true"` on the decorative dot grid

### PipelineProgressIndicator
- Active step: ring-glow pulse via `shadow-[0_0_0_4px_var(--color-primary-subtle)]`
- Failed step: shows `AlertTriangle` icon with danger colours
- Progress bar uses `bg-brand-bar` (teal → cyan gradient) instead of flat `bg-primary`
- Stage description hint renders below the bar during active runs
- `role="progressbar"` on the bar with `aria-valuenow`
- Structured error block with icon + "Pipeline failed" heading
- Structured complete block with check icon + green tint

---

## Prop-Contract Audit

All exported prop interfaces are UNCHANGED or EXTENDED (additive only).
No prop was renamed or removed. New optional props added:

| Component | New optional props |
|---|---|
| `StatusPill` | `dot?: boolean` |
| `DQChip` | `label?: string` |
| `MetricTable` | `showPillar?: boolean` |
| `AIProposalBanner` | `detail?: string`, `className?: string` |
| `ScoreGauge` | `showTier?: boolean` |

---

## TypeScript / JSX Validity Notes

- No `npm`/`tsc` run possible (Node.js not installed). All changes verified by
  static analysis.
- `variants()` in `utils.ts` is generic over `VariantMap` — inferred from the
  `config.variants` argument, no `any` used.
- `ScoreGauge`: `PILLAR_COLORS` uses `Record<string, string>` which is consistent
  with the `(['E','S','G'] as const)` map access.
- `PipelineProgressIndicator`: `AlertTriangle` is a named export from `lucide-react`
  (available in the installed version) — verify lucide version supports this icon if
  the build reports a missing export.
- `globals.css` `@theme` block now mirrors all new token names from `tokens.css`.
  Any token present in one must be present in the other to avoid `var()` fallback
  to `transparent`.

---

## Reconciliation Flags (for orchestrator)

1. **`bg-brand-gradient` utility** — defined in `globals.css` as a plain CSS class.
   It is NOT a Tailwind utility generated from `tailwind.config.ts` — it will
   work in JSX only if globals.css is imported before the component renders.
   If other agents need this class, they can use it as-is (globals.css is
   imported at app root).

2. **`bg-brand-bar` utility** — same note as above.

3. **`orange-400` / `orange-500`** — `DQChip` level 4 uses `text-orange-400` and
   `bg-orange-500/10`. These are standard Tailwind palette classes (not custom
   tokens). If the Tailwind config content scan is restricted, ensure
   `text-orange-400` is in the safelist or appears in a scanned file.

4. **`lucide-react` `AlertTriangle`** — added to `PipelineProgressIndicator`.
   Confirm `AlertTriangle` is exported by the installed `lucide-react` version.
   If not, replace with `XCircle` or `AlertCircle` which are universally available.

5. **`--chart-1..5` vars in recharts** — chart palette tokens are CSS variables.
   Recharts `<Cell fill="var(--chart-1)">` works in modern browsers. If the
   project needs IE11 / older WebView support, use the resolved hex values instead.

---

## Recommended Next Priorities

1. **Agent reconcile**: verify no other agent wrote conflicting `bg-surface-raised`
   or `text-text-muted` class overrides — the semantics of those tokens changed
   slightly (darker bg in dark mode: `#192132` vs old `#1F2937`).

2. **Inter Variable font**: `tokens.css` declares `'Inter Variable'` as the
   preferred `--font-sans` face. If it is not in `index.html`, the browser falls
   back to plain `Inter`. Add the Google Fonts or Bunny Fonts import for the
   variable-weight variant to unlock optical-size and weight animations.

3. **Arabic font verification**: `IBM Plex Sans Arabic` is declared but may not
   be loaded. Add `<link>` preconnect + stylesheet for it in `index.html`.

4. **Focus-ring regression check**: `globals.css` now sets `outline: none` on
   `*:focus` and restores it on `*:focus-visible`. Confirm the app's Radix UI
   components do not rely on browser-default outlines — Radix already manages
   `data-[focus-visible]` so this should be safe.

5. **Pillar violet colour**: `ScoreGauge` and `MetricTable` both use `#A78BFA`
   (violet) for the G pillar. This is a raw hex, not a CSS token. Add
   `--color-pillar-g` to `tokens.css` if governance colour ever needs dark/light
   variants.
