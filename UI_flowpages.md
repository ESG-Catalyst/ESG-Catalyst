# UI Flow Pages — Agent 3 Deliverable

## Pages changed

### 1. `frontend/react/src/pages/Landing.tsx`

**What changed**
- Hero: added regulatory trust badge (FRA · CBE · GRI Aligned pill), feature bullet-list with CheckCircle2 icons before the CTA block, ArrowRight icon on primary CTA, subtle second radial glow at bottom-left for depth, and a decorative ring around the ScoreGauge.
- HowItWorks: replaced the vertical timeline with a 3-column grid — each step shows the step-number bubble + category icon + text. Removed the physical `left-` absolute connector line, added a horizontal decorative connector only on desktop.
- RegulatoryStrip: added icon per regulation card, used `borderStartWidth`/`borderStartColor` (logical) instead of physical `borderLeft`/`borderLeftColor` so the accent line flips correctly in RTL.
- Pricing: fixed physical `ml-1` → `ms-1` on the price period; replaced `<a>` with `<Link>` for internal plan CTA links; added hover `translate-y-1` lift on cards; `aria-label` on "Most Popular" badge.
- BottomCTA: added Zap icon in a teal ring above the heading, split CTA into primary button + secondary "Talk to an expert" link, ArrowRight icon on button.
- Contact: refactored the 3 input fields into a map to reduce repetition; added `id`/`htmlFor` pairing for accessibility; added `autoComplete` attributes.
- Footer: expanded to a two-column responsive layout with links.
- Navbar: added `focus-visible:ring-2 ring-primary` to all interactive elements; wrapped nav in `<nav aria-label="Main navigation">`; `aria-label` on language toggle button.
- Wrapped all page content in `<main>` semantic element.
- All section headings given `id`+`aria-labelledby` for landmark navigation.

**New UX**
- Trust framing for regulated-finance audience: regulatory badge in hero, per-regulation icons, feature bullets with checkmarks instead of bare text.
- Feature parity: HowItWorks is now a scannable 3-column grid rather than a scroll-heavy vertical timeline.
- Stronger hierarchy: section labels, then heading, then supporting copy throughout.

---

### 2. `frontend/react/src/pages/Upload.tsx`

**What changed**
- Added `motion` (framer-motion) import; upload icon animates `scale: 1.1` on drag-over.
- Dropzone: `background` and `boxShadow` transition on drag-over; dynamic copy ("Drop to upload" while dragging); file-format badges rendered as pill chips instead of a plain text string; file-count badge (top-end corner) shows `X/5` once files are selected; `aria-label` describes the current action.
- `<input type="file">` changed to `className="sr-only"` (screen-reader accessible) instead of `className="hidden"`.
- File row: added `FileTypeBadge` sub-component showing coloured EXT badge; status icon (`CheckCircle2`) for valid files; per-file warning rendered with `Info` icon + amber border (instead of the old collective banner); error/warning border colour on the row itself.
- Collective image warning: only shown for `imageCount > 1` (individual warnings already inline per row).
- Upload progress: `isUploadComplete` state drives colour change to green + "Upload complete — starting analysis…" message with a `CheckCircle2` icon.
- Submit button: `py-3` + `rounded-lg` for a more prominent CTA; `aria-busy` attribute; stronger disabled state message.
- `extractErrorMessage` moved to top-level (before the component) for clean module structure.
- `role="alert"` on server-error banner and per-file error paragraphs.

**New UX**
- Drag state is clearly communicated visually (glow ring, scale animation, copy change).
- Users see exactly what file types are accepted via chips, not a comma-separated string.
- Valid files show a green checkmark; errored files show a red border; warned files show amber border — no ambiguity.
- Upload progress completion is obvious before the page navigates.

---

### 3. `frontend/react/src/pages/PipelineProgress.tsx`

**What changed**
- Header: dynamic title changes to "Analysis Complete" / "Analysis Failed" / "Analysis in Progress" based on state.
- Document label: reads `storedDocName` from `usePipelineStore` (already in store shape) and shows the filename instead of a truncated UUID when available.
- Error empty state: improved with "Try refreshing" hint + monospace job ID.
- Complete state: `role="status" aria-live="polite"` for screen-reader announcement; `aria-label` on CTA link; CheckCircle2 icon replaces the `→` arrow.
- Failed state: `role="alert" aria-live="assertive"` for immediate screen-reader announcement; retry button has `focus-visible:ring-2`; contact link has `focus-visible` ring.
- `font-mono` on the OpenRouter URL in error tip (instead of the `font-mono` class which wasn't in the token set).
- `flex-wrap` on the failed-state action row so buttons don't overflow on small screens.
- All icon-only decorative icons given `aria-hidden="true"`.

**New UX**
- Page title is self-describing — a user who tabs back sees "Analysis Complete" not the static "Analysis in Progress".
- Filename from the pipeline store gives meaningful context without exposing the raw UUID.
- Screen readers are told immediately when the pipeline fails (assertive live region) vs completes (polite).

---

### 4. `frontend/react/src/pages/Results.tsx`

**What changed**
- Header copy: "Approve AI-extracted metrics before generating your ESG report" (clearer action framing).
- Empty state (no documentId): replaced bare text with a centered card — icon, heading, and call-to-action hint.
- Filter bar: `role="toolbar"` on the outer bar; `role="tablist"` + `aria-label` on the status pill row; `role="tab"` + `aria-selected` on each tab button; `role="group"` + `aria-label` on the pillar filter; `aria-pressed` on each pillar button; search changed to `type="search"` + `aria-label`; focus border highlight on search input.
- Bulk actions: `ms-auto` (RTL-safe) instead of `ml-auto`.
- Metric card action buttons: `aria-label` includes the GRI code ("Approve GRI 302-1"); `aria-pressed` on approve/reject; `aria-expanded` on edit toggle; `focus-visible:ring-2` on all three.
- Bottom bar: `role="toolbar" aria-label="Report actions"`; copy changed from "reviewed" to "approved" (more precise); `ms-2` on pending-review count instead of `ml-2`; `aria-busy` + `aria-disabled` on Generate Report button; `title` tooltip when disabled.
- EvidenceViewer: `mr-1` → `me-1` + `aria-hidden` on FileText icon.

**New UX**
- Full keyboard navigation for the filter controls with correct ARIA roles.
- Bulk action buttons are logically positioned (float to logical-end, RTL-safe).
- Metric actions are meaningfully labelled for screen readers.
- Generate Report button communicates its disabled reason via `title` tooltip.

---

### 5. `frontend/react/src/pages/ReportView.tsx`

**What changed**
- No-report empty state: replaced bare text with a centered card with icon, heading, and guidance.
- Download button: `aria-busy` + dynamic `aria-label` (includes filename when available); "Downloading…" label while in-flight; `focus-visible:ring-2`.
- Share button: `aria-label` reflects copied vs uncopy state; `role="status"` on the "Coming soon" message.
- Both drag handles: `role="separator" aria-orientation="vertical"` + `aria-label` + `tabIndex={0}` + `onKeyDown` stub for future keyboard nudging.
- Tab bar: `role="tablist" aria-label="Report sections"`; each button has `role="tab"`, `aria-selected`, `id`, and `aria-controls`.
- Tab panel: `role="tabpanel"`, `id`, and `aria-labelledby` wired to the correct tab button.
- PDF preview panel: `aria-label="PDF preview panel"` on container; filename shown in the panel header bar (`ms-auto`, RTL-safe).
- `ml-auto` → `ms-auto` in `PreviewTab` pillar section header.
- All decorative icons given `aria-hidden="true"`.

**New UX**
- Tab keyboard accessibility: correct ARIA tablist/tab/tabpanel triad so screen readers announce the selected section correctly.
- PDF panel header now shows the filename so users know what they're previewing.
- Drag handles are focusable and have meaningful labels — screen readers can discover them.

---

## Shared-component prop gaps flagged for Agent 1

None of the edits required changing shared component props. The following components were used as-is:
- `ScoreGauge` — used with existing `scores` + `overall` + `size` props.
- `StatusPill` — used with existing `status` prop.
- `FrameworkCoverageBar` — not used in these pages (lives in ReportView sidebar — no changes to that component call).
- `DQChip` — not used in these pages.

**Potential Agent 1 enhancement requests** (flagged, not implemented):
- `StatusPill` could accept an optional `aria-label` prop to override the visible text label for screen readers (e.g. "Metric status: approved").
- `ScoreGauge` does not appear to have an `aria-label` or `role` — it would benefit from a summary text for screen readers (e.g. "Overall ESG score: 66. Environmental: 72, Social: 58, Governance: 65").

---

## Reconciliation notes

- No route changes, no react-query key changes, no store shape changes, no `api/` changes. All data wiring preserved exactly.
- `motion` import added to `Upload.tsx` (already a project dependency — no new dep).
- `Info`, `CheckCircle2`, `ArrowRight`, `Shield`, `Zap`, `FileCheck` lucide icons added to Landing (all part of `lucide-react` already installed).
- `Info`, `CheckCircle2` added to Upload (same package).
- Physical Tailwind utilities replaced with logical equivalents: `ml-` → `ms-`, `mr-` → `me-`, `left-0 right-0` → `inset-x-0` (already used), `borderLeft` → `borderStart` in inline styles.
- `<a href>` for internal routes in Pricing section changed to `<Link>` (react-router) to avoid full-page reload.

---

## Recommended next priorities

1. **`ScoreGauge` a11y** — add visually hidden summary text so screen readers can announce the E/S/G breakdown without requiring visual inspection.
2. **`StatusPill` a11y** — optional `aria-label` override prop.
3. **Landing i18n** — all hero/feature copy is hard-coded English; future AR pass should extract to i18n keys.
4. **`PipelineProgress` keyboard nudge** — the drag handle `onKeyDown` stubs need `useResizable`/`useResizableInner` to expose an imperative setter so ArrowLeft/Right can actually resize (currently fires `preventDefault` only).
5. **Results `MetricCard` expand/collapse** — the card `onClick` to expand evidence runs on the whole card; this is a11y-risky since the card has interactive children. Consider wrapping the non-button area in a `<button>` with explicit keyboard focus, or making the card header the only clickable expand target.
