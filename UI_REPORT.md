# ESG Catalyst — Frontend UI/UX Enhancement Report

**Branch:** `test-opus` (`main` untouched)
**Date:** 2026-06-03
**Method:** 5 parallel worktree-isolated subagents (design-system / shell-nav / flow-pages / account-pages / i18n+audit), reconciled centrally and verified with a real `type-check` **and** production `build`.

> UI/UX only. No routes, react-query keys, API clients, store shapes, or business logic changed — restyle/restructure + a11y/RTL/i18n. `models/`, `schemas/`, and the whole `backend/` were untouched.

---

## 1. Verification (the strong part)

Node v26 + `node_modules` are present on this host (contrary to old session notes), so this was verified by the **actual compiler**, not static reading:

| Gate | Result |
|---|---|
| `tsc --noEmit` (type-check) | ✅ exit 0 |
| `tsc -b && vite build` (production build) | ✅ exit 0 — **2,109 modules**, `dist` CSS 46 KB / JS 886 KB, built in 6.25 s |

Baseline `type-check` was clean before the work; the merged result is clean after. The build surfaced exactly **one** UI bug (fixed) + a pre-existing infra gap (fixed) — see §3.

---

## 2. What changed, by area (~5,200 insertions, 38 files)

### 1 · Design system & primitives (`components/ui/**`, `styles/**`, `tailwind.config.ts`, `lib/utils.ts`)
Refined the token palette (richer dark contrast, light parity), **added** a shadow scale, `chart-1..5` palette, focus-ring + brand-gradient tokens, `radius-xl`, and a `prefers-reduced-motion` guard in `globals.css`. Polished all 7 primitives (StatusPill, DQChip, MetricTable, AIProposalBanner, ScoreGauge, FrameworkCoverageBar, PipelineProgressIndicator) with consistent elevation/spacing, hover/focus states, and ARIA roles (`role="meter"/"progressbar"/"status"`). **All prop contracts preserved** (new props additive); a `variants()` helper added to `lib/utils.ts`.

### 2 · Shell / nav / theme / RTL (`components/layout/**`, `ErrorBoundary`, `App.tsx`, `store/ui.ts`)
Fixed the **`dir`/`lang` wiring gap**: `<html dir/lang>` now syncs from the language store at init, rehydrate, and every toggle (no RTL flash-of-unstyled-content). Sidebar rewritten (RTL-correct via logical `insetInlineStart/End`, smooth collapse), real **mobile off-canvas drawer** (`<md`), sticky blurred TopBar with hamburger + breadcrumbs, framer-motion route transitions, branded ErrorBoundary. `store/ui.ts` extended additively; `router.tsx` untouched.

### 3 · Core flow pages (`Landing, Upload, PipelineProgress, Results, ReportView`)
Landing: trust-framed hero (FRA·CBE·GRI badge), 3-column "how it works", regulatory strip, expanded footer. Upload: drag-state visuals, format chips, per-file status/warn/error rows, completion state. PipelineProgress: self-describing title, filename from store, polite/assertive live regions. Results: full filter-bar ARIA (`tablist`/`toolbar`), labelled per-metric actions, RTL-safe bulk actions. ReportView: proper tab `tablist/tab/tabpanel` triad, focusable resize handles, filename in PDF header. **All data wiring identical.**

### 4 · Account / dashboard / portal (`auth/Login, auth/Register, Dashboard, ConsultantWorkspace, Admin`)
Auth: `label htmlFor`/`aria-describedby`, password show/hide + strength meter, focus rings. Dashboard: score cards with stat chips, recharts using the new chart tokens, skeletons + empty states. Consultant: search + animated modal. Admin: avatar initials, animated role selector, self-row protection, stats skeletons. **All form/role/query wiring identical.**

### 5 · i18n + document head + audit (`i18n/en.json`, `i18n/ar.json`, `index.html`, `UI_audit.md`)
Expanded **en + ar** bundles to near-complete parallel coverage (nav, auth, upload, pipeline, metrics, report, dashboard, consultant, admin, landing, status/tier, errors, common) — all existing keys preserved. `index.html` got proper `lang/dir`, title/meta/theme-color, and font loading (Inter / IBM Plex Sans Arabic / JetBrains Mono). Plus an 8-section cross-cutting **a11y/RTL/responsive audit** (`UI_audit.md`).

Per-area detail: `UI_designsystem.md`, `UI_layout.md`, `UI_flowpages.md`, `UI_accountpages.md`, `UI_audit.md`.

---

## 3. Reconciliation fixes (central)

1. **`Landing.tsx` — invalid React style keys.** Agent 3 used `borderStartWidth`/`borderStartColor` in an inline `style={{}}` (intended RTL-logical, but not valid `CSSProperties`). Corrected to `borderInlineStartWidth`/`borderInlineStartColor` — the build's only UI error.
2. **`@types/node` (pre-existing gap).** `vite.config.ts` (untouched by this work) uses `path`/`process`/`__dirname` but `@types/node` was never installed, so `tsc -b` was already red on `main`. Added `@types/node` as a devDependency so the production build is fully green.

---

## 4. Process note — two transient `529`s
Agents 3 (flow pages) and 5 (i18n/audit) hit `API Error: 529 Overloaded` on their **final summary message** only — their file edits were already written and committed in their worktrees. The compiler gate (type-check + build green) confirms their work is complete and valid; their deliverable docs (`UI_flowpages.md`, `UI_audit.md`) are intact.

---

## 5. Backlog (from `UI_audit.md`, de-duplicated)
The audit ran against the **pre-enhancement baseline**, so many items (focus rings, ARIA roles, logical utilities) were already delivered by agents 1–4 in parallel. The genuinely-open items worth a follow-up pass:

1. **Reduced-motion in pages** — Agent 1 added the CSS-variable guard, but page-level framer-motion (`Landing`, `PipelineProgress` ChunkGrid, etc.) should use `useReducedMotion()`.
2. **Responsive stacking** — `ReportView` split-pane and `Results` evidence panel are still desktop-only below `lg`; stack vertically / use a drawer on mobile/tablet.
3. **Light-mode contrast** — re-check `text-text-subtle` (#94A3B8 on white ≈ 4.0:1) at `text-xs`; bump toward #6B7280, and replace remaining literal `#F59E0B` with `var(--color-warning)`.
4. **Dashboard error state** — handle `isError` (esp. 401 → "sign in again").
5. **Focus trap** — `ConsultantWorkspace` AddClientModal + `Admin` RoleSelector should use Radix `Dialog`/`DropdownMenu` (already in deps) for focus trap + Escape.
6. **i18n adoption** — bundles are now complete, but several pages (notably Landing) still hard-code English; wire `t()` to the new keys.
7. **Bundle size** — JS chunk 886 KB; consider route-level `lazy()` + `manualChunks` (build warns >500 KB).

---

## 6. Commit map (on `test-opus`)
```
8ba93cd  fix(ui): valid logical inline-style props in Landing; add @types/node so vite.config type-checks
5efd7aa  feat(ui): expand en/ar i18n coverage + index.html fonts/meta; add UI audit
75ffa76  feat(ui): restyle auth/dashboard/consultant/admin pages
fcf238c  feat(ui): restyle core flow pages (landing/upload/pipeline/results/report)
5776228  feat(ui): polish app shell/nav; wire dir/lang from language; mobile drawer + route transitions
871782f  feat(ui): polish design tokens + 7 UI primitives (shadow scale, chart palette, a11y roles)
```

## 7. Not done (by design)
- **Visual/interaction QA** — verified to compile + build, *not* visually rendered. Recommend `npm run dev` + a browser pass (I can drive this next if you want).
- The §5 backlog (a deliberate follow-up list, not regressions).
