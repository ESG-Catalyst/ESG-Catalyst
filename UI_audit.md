# ESG Catalyst React Frontend — UI/UX Audit
Agent 5 deliverable (i18n + index.html + cross-cutting UX/a11y/RTL recommendations)

---

## 1. RTL — Physical vs Logical CSS Utilities

### 1a. Sidebar position uses physical `left-0` / `right-0` conditionally in JS
**File:** `frontend/react/src/components/layout/Sidebar.tsx` (line 96, 108)
**Issue:** `const sideEdge = isRTL ? 'right-0' : 'left-0'` — a JS string switch instead of the Tailwind logical utility `start-0`. Any future responsive changes must remember to duplicate this RTL branch.
**Fix:** Replace with `start-0` (Tailwind v3.3+ logical utility). Tailwind automatically flips `start` to `right` in RTL documents — no JS needed. Remove the `isRTL` branch for the position.

### 1b. `marginLeft` / `marginRight` swap in AppShell
**File:** `frontend/react/src/components/layout/AppShell.tsx`
**Issue:** The main content area applies `marginLeft` or `marginRight` via inline style based on `language === 'ar'`. Physical `marginLeft`/`marginRight` require JS to flip and will break if a third language or auto-detect is added.
**Fix:** Use CSS logical property `margin-inline-start` (Tailwind: `ms-[var(--sidebar-width)]`) which auto-flips in RTL without JS. Remove the language check from AppShell.

### 1c. `borderLeft` / `borderRight` physical properties in Sidebar styles
**File:** `frontend/react/src/components/layout/Sidebar.tsx` (inline style object, line 112)
**Issue:** `[isRTL ? 'borderLeft' : 'borderRight']: '1px solid var(--color-border)'` — computed property key that toggles physical border. Same JS-duplication problem.
**Fix:** Use `borderInlineEnd: '1px solid var(--color-border)'` (logical property). No JS check needed; the browser flips it in RTL.

### 1d. Active nav indicator uses `[isRTL ? 'right' : 'left']: 0`
**File:** `frontend/react/src/components/layout/Sidebar.tsx` (NavItem, line 83)
**Issue:** Explicit physical side via computed key.
**Fix:** Use `insetInlineStart: 0` (CSS logical) or Tailwind `start-0` on the indicator span. The `left: 0` absolute indicator will naturally appear on the correct side without JS.

### 1e. `text-left` class hardcoded in Admin, ConsultantWorkspace table cells
**Files:** `frontend/react/src/pages/Admin.tsx`, `frontend/react/src/pages/ConsultantWorkspace.tsx`
**Issue:** `text-left` is a physical utility. In AR/RTL mode, table text will be left-aligned (which is actually start-aligned in LTR but end-aligned in RTL visually) — but because Tailwind's RTL variant is not applied, it stays physically left-aligned, which looks reversed.
**Fix:** Replace `text-left` with `text-start` on table header and cell elements. Tailwind maps `text-start` to `text-align: start` which browser resolves correctly in both directions.

### 1f. `ms-5` used in Register.tsx (positive, correct) — confirm usage
**File:** `frontend/react/src/pages/auth/Register.tsx` (line 194)
**Status:** `ms-5` is correct usage of the logical `margin-inline-start`. No change needed.

---

## 2. Color Contrast and Theme Parity

### 2a. Hard-coded rgba overlays lose readability in light theme
**Files:** Multiple pages — e.g. `PipelineProgress.tsx`, `Results.tsx`, `ReportView.tsx`
**Issue:** Error/warning banners use hard-coded `rgba(239,68,68,0.08)` backgrounds. In light theme (`--color-bg: #FAFAFA`) these are often borderline: `rgba(239,68,68,0.08)` on white gives a nearly-white tint with `color: #EF4444` — passes contrast in isolation, but the `text-xs` body copy inside (`color: var(--color-text-muted)` = `#475569` on white) gives 4.5:1 only marginally. The warning box in `Upload.tsx` uses `color: '#F59E0B'` (amber) on near-white — fails WCAG AA at small text sizes.
**Fix:** Use semantic CSS tokens (`--color-warning`, `--color-danger`) from `tokens.css` which are already calibrated per theme. Add `--color-warning-bg` and `--color-danger-bg` tokens (e.g. light = `#FEF3C7` / dark = `rgba(245,158,11,0.10)`) so banners use the token, not a hard-coded rgba.

### 2b. `text-text-subtle` on card backgrounds in light mode may fail contrast
**Files:** `Dashboard.tsx`, `Results.tsx`, `ReportView.tsx` (multiple instances of `text-text-subtle`)
**Issue:** `--color-text-subtle` in light theme is `#94A3B8` on `#FFFFFF` (4.04:1). WCAG AA requires 4.5:1 for small text. Many labels and meta-info use `text-text-subtle` at `text-xs` (12px effective) which is "small text".
**Fix:** Raise `--color-text-subtle` in light theme from `#94A3B8` to `#6B7280` (5.74:1 on white). Review any component currently using `text-text-subtle` for non-decorative text.

### 2c. `#F59E0B` (amber warning text) on dark backgrounds is fine but needs verification on light
**Issue:** `--color-warning` is `#F59E0B` in dark theme (9.3:1 on `#111827`). In light theme it is overridden to `#B45309` (tokens.css line 70). Check that all places using the literal `#F59E0B` (not the token) switch appropriately. At least 8 locations use the literal hex directly in JSX.
**Fix:** Replace every `color: '#F59E0B'` in JSX with `color: 'var(--color-warning)'`.

---

## 3. Focus Management and Keyboard Navigation

### 3a. Drop zone in Upload.tsx is keyboard-accessible but only for `Enter`/`Space`
**File:** `frontend/react/src/pages/Upload.tsx` (line 214)
**Issue:** `onKeyDown` handles Enter and Space — correct. However, the `role="button"` element also needs `aria-disabled` when `!zoneClickable` (currently uses `tabIndex={-1}` which removes it from tab order entirely but doesn't inform AT that it exists in a disabled state).
**Fix:** Keep `tabIndex={-1}` when disabled but also add `aria-disabled="true"` so screen-reader users browsing by role still understand the element exists.

### 3b. Modal in ConsultantWorkspace lacks focus trap
**File:** `frontend/react/src/pages/ConsultantWorkspace.tsx` — `AddClientModal` component
**Issue:** When the modal opens, focus is not moved into the modal dialog. A keyboard user (or screen-reader user in virtual cursor mode) can navigate behind the modal overlay, potentially activating buttons on the page underneath.
**Fix:** On mount, `useEffect` should `ref.current?.focus()` the modal container (which should have `tabIndex={-1}`) or the first focusable element inside. On unmount, restore focus to the trigger button. Alternatively, use Radix `Dialog` primitive (already in the stack) which provides focus trap and `aria-modal` automatically.

### 3c. Drag handle in ReportView has no keyboard equivalent
**File:** `frontend/react/src/pages/ReportView.tsx` — `useResizable` / drag handle `<div>`
**Issue:** The `onMouseDown` resize handle is a non-interactive `<div>`. Keyboard users cannot resize the split pane.
**Fix:** Add `role="separator"` + `aria-orientation="vertical"` + `aria-valuemin`/`aria-valuemax`/`aria-valuenow` attributes. Handle `onKeyDown` Arrow Left/Right (adjust `leftPct` by 2% per key press). This matches the ARIA authoring guide for `separator` widgets that are focusable.

### 3d. Dropdown in RoleSelector (Admin.tsx) lacks focus management and Escape key
**File:** `frontend/react/src/pages/Admin.tsx` — `RoleSelector` component
**Issue:** Clicking outside closes the dropdown via overlay div, but pressing Escape does not. Focus is not trapped inside the open dropdown, and when it closes the focus should return to the trigger button.
**Fix:** Add `onKeyDown` handler: `Escape` → `setOpen(false)` + return focus to trigger. Arrow Down/Up should move focus between role options (role="option" elements). Alternatively, replace with Radix `DropdownMenu` primitive.

### 3e. MetricCard action buttons have no focus-visible ring in custom styles
**File:** `frontend/react/src/pages/Results.tsx` — `MetricCard` approve/reject/edit buttons
**Issue:** Buttons use inline `style` for borders but no `:focus-visible` ring is defined. Tailwind's default `focus:ring` classes are not applied, so keyboard focus on these buttons is invisible.
**Fix:** Add `focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary` (or the Tailwind equivalent using CSS custom property) to each action button in MetricCard.

---

## 4. Form Labeling

### 4a. `<label>` elements in Login, Register, Results EditForm use static `<label>` with no `htmlFor`
**Files:** `frontend/react/src/pages/auth/Login.tsx`, `Register.tsx`, `frontend/react/src/pages/Results.tsx`
**Issue:** The `Field` helper renders `<label className="...">{label}</label>` directly above the input, relying on DOM proximity instead of explicit `htmlFor`/`id` association. Screen readers using "Forms mode" may not announce the label when the input is focused.
**Fix:** Generate an `id` prop for each input (e.g., `id="field-email"`) and add `htmlFor="field-email"` to the `<label>`. The `Field` component should accept an `id` prop or auto-generate one via a counter/crypto.

### 4b. Select element in Register has no visible label in collapsed state
**File:** `frontend/react/src/pages/auth/Register.tsx` (institution_type select, line 162)
**Issue:** Static `<label>Institution type</label>` without `htmlFor` — same as 4a. Additionally the `<select>` is visually styled with `appearance-none` but has no custom indicator, making it hard to identify as a select in light theme.
**Fix:** Same `htmlFor`/`id` association. Consider adding a chevron icon overlay for the `appearance-none` select.

### 4c. Search inputs in Admin and Results pages have no `<label>`
**Files:** `frontend/react/src/pages/Admin.tsx` (line 214), `frontend/react/src/pages/Results.tsx` (line 681)
**Issue:** Search `<input>` elements use `placeholder` only — not accessible as a label because placeholder disappears when the user types and has no semantic weight.
**Fix:** Add `<label className="sr-only" htmlFor="search-input">Search</label>` (visually hidden) and `id="search-input"` on each search input. Alternatively add `aria-label="Search users"` directly on the input.

### 4d. EditForm in Results.tsx uses `<label>` without `htmlFor`
**File:** `frontend/react/src/pages/Results.tsx` — `EditForm` component (lines 102, 118, 138)
**Issue:** Three `<label>` elements (Value, Unit, Reason for edit) have no `htmlFor`.
**Fix:** Add `id` to each input and matching `htmlFor` on each label.

---

## 5. Loading, Empty State, and Error State Coverage

### 5a. PipelineProgress — no loading skeleton while query is pending
**File:** `frontend/react/src/pages/PipelineProgress.tsx`
**Issue:** The `useQuery` for pipeline status shows nothing until data arrives or an error fires. First render is a blank page for a few hundred milliseconds.
**Fix:** Add a simple skeleton or spinner state for `isLoading === true` (query has not yet resolved) — distinct from the "could not load status" error state.

### 5b. ConsultantWorkspace uses mock data — no loading/error state
**File:** `frontend/react/src/pages/ConsultantWorkspace.tsx`
**Issue:** `MOCK_CLIENTS` is hardcoded; no API call is made, so no error state is needed now. However once the real API is wired, the component has no loading/error UI.
**Fix:** Accept as a known future gap. Add a `TODO` comment marking where `useQuery` should go and where error/empty states should render.

### 5c. ReportView GeneratingState — timeout warning shown but no actionable path
**File:** `frontend/react/src/pages/ReportView.tsx` — `GeneratingState` (line 67)
**Issue:** After 300s a timeout warning is shown with no retry button or contact-support link. The user is stuck waiting indefinitely.
**Fix:** Add a "Contact Support" link (same mailto as PipelineProgress) or "Retry" link (navigate back to `/results/{docId}`) when `isTimedOut === true`.

### 5d. Dashboard error state is absent
**File:** `frontend/react/src/pages/Dashboard.tsx`
**Issue:** `useQuery` calls for documents, metrics, and reports have no `isError` handling. If the API returns 401 (expired token) the page silently shows the empty state or skeleton forever.
**Fix:** Check `isError` on the documents query; if true, show an inline error card with a "Sign in again" link pointing to `/auth/login`.

---

## 6. Responsive Breakpoints

### 6a. ReportView split-pane is not responsive below `lg`
**File:** `frontend/react/src/pages/ReportView.tsx`
**Issue:** The horizontal split pane (`flex h-screen`) is unusable on viewport widths below ~900px. On mobile the PDF preview panel would be ~42% of a 375px screen (~157px wide), rendering nothing useful.
**Fix:** Below `lg` (< 1024px), stack the layout vertically: hide the drag handle, use `flex-col` on the outer wrapper, and stack `left panel` above `PDF preview`. Use a tab or toggle to show/hide the PDF on small screens.

### 6b. Results two-column layout hides the evidence viewer on all non-large screens
**File:** `frontend/react/src/pages/Results.tsx` (line 761: `className="hidden lg:block"`)
**Issue:** The evidence viewer is completely hidden below `lg`. On tablet (768–1023px) users lose the evidence panel entirely.
**Fix:** For `md`–`lg` viewports, consider a slide-out drawer or bottom sheet for the evidence viewer, triggered when a metric card is selected, rather than hiding it entirely.

### 6c. Landing hero ScoreGauge hidden on mobile
**File:** `frontend/react/src/pages/Landing.tsx` (line 160: `flex justify-center lg:justify-end`)
**Issue:** The `lg:grid-cols-2` hero collapses to a single column on mobile, but the gauge row still renders and may be very large (default `size="lg"`). Consider setting `size="md"` on smaller screens or hiding the gauge and showing only the copy on mobile.
**Fix:** Wrap the ScoreGauge `FadeIn` with `hidden sm:flex` or pass a responsive `size` prop if the component supports it. Review `ScoreGauge.tsx` for responsive sizing.

---

## 7. Motion and Reduced-Motion

### 7a. No `prefers-reduced-motion` guard on framer-motion animations
**Files:** `Landing.tsx`, `PipelineProgress.tsx`, `Results.tsx`, `ReportView.tsx`, `ConsultantWorkspace.tsx`
**Issue:** All `motion.div` animations (fade-in on scroll, pulsing icons, step completion bounce) run unconditionally. Users with vestibular disorders or motion sensitivity who have set `prefers-reduced-motion: reduce` in OS settings get full animations.
**Fix:** Use framer-motion's `useReducedMotion()` hook. Wrap animation variants: if `shouldReduceMotion` is true, use `initial={{ opacity: 1 }}` / `animate={{ opacity: 1 }}` (instant) and `transition={{ duration: 0 }}`. Apply at the `App.tsx` root level by providing a motion config, or at individual component level for complex animations like the pipeline step pulses and the landing hero.

### 7b. ChunkGrid animation (PipelineProgress) always runs at full speed
**File:** `frontend/react/src/pages/PipelineProgress.tsx` — `ChunkGrid`
**Issue:** 80 squares animate with `background` transitions during classification. With `prefers-reduced-motion: reduce` this is distracting.
**Fix:** Wrap the `animate` prop on each square with a ternary: if reduced motion, skip the background transition (`transition={{ duration: 0 }}`).

### 7c. CSS transitions on `tokens.css` `--transition-*` variables have no reduced-motion override
**File:** `frontend/react/src/styles/tokens.css`
**Issue:** `--transition-fast`, `--transition-base`, `--transition-slow` are defined but there is no `@media (prefers-reduced-motion: reduce)` block that sets them to `0ms none`.
**Fix:** Add:
```css
@media (prefers-reduced-motion: reduce) {
  :root {
    --transition-fast: 0ms none;
    --transition-base: 0ms none;
    --transition-slow: 0ms none;
  }
}
```
This instantly covers all usages of the CSS variables without touching each component.

---

## 8. Miscellaneous A11y

### 8a. `<table>` in Dashboard MetricsSummaryTable has no `<caption>` or `aria-label`
**File:** `frontend/react/src/pages/Dashboard.tsx` — `MetricsSummaryTable`
**Issue:** Screen readers announce the table without a descriptive name; the user has to traverse the headers to understand context.
**Fix:** Add `<caption className="sr-only">Extracted ESG metrics for {documentName}</caption>` as the first child of `<table>`.

### 8b. StatusPill component has no ARIA role for color-only information
**File:** `frontend/react/src/components/ui/StatusPill.tsx`
**Issue:** Status information is conveyed via background color and label text. The label text is accessible, but there is no `aria-label` on the pill for assistive tech that doesn't read small color-coded badges.
**Status:** The text label is present and readable — this is actually fine. No change needed unless the label is truncated.

### 8c. `<mark>` highlight in EvidenceViewer is not announced as a highlight to AT
**File:** `frontend/react/src/pages/Results.tsx` — `highlightEvidence`
**Issue:** `<mark>` has implicit `role="mark"` in ARIA 1.3 but NVDA/JAWS support is inconsistent. The user may not realize the value is highlighted.
**Fix:** Add `aria-label` on the `<mark>` element, e.g. `aria-label={`Matched value: ${part}`}`. This is a minor enhancement; the text itself is still readable without it.

### 8d. Icon-only buttons lack accessible labels
**Files:** Multiple — e.g. Upload page remove button (`aria-label={`Remove ${s.file.name}`}` — CORRECT), but Admin `RefreshCw` button (line 195: `title="Refresh"` only — no `aria-label`).
**Issue:** `title` is announced by some AT but is not reliable on mobile/touch. `aria-label` is required.
**Fix:** Add `aria-label="Refresh user list"` to the Admin refresh button. Audit all icon-only buttons across the app for missing `aria-label`.

### 8e. Iframe for PDF preview lacks a meaningful `title`
**File:** `frontend/react/src/pages/ReportView.tsx` — `PdfPreview` (line 793)
**Issue:** `title="PDF Preview"` — generic. Screen readers announce this when the user enters the frame.
**Fix:** Pass the report filename as part of the title: e.g., `title={`ESG Disclosure Report PDF — ${reportDate}`}`.

---

## 9. i18n Keys Added (Agent 5 summary)

The following top-level keys are **new** relative to the original en/ar bundles.
Page agents can adopt them via `t('key.subkey')`:

| New top-level key | Description |
|---|---|
| `nav.expand`, `nav.tools`, `nav.home` | Sidebar expand + section heading |
| `auth.confirmPassword`, `auth.institutionName`, `auth.institutionType`, `auth.remember_me`, `auth.forgot_password`, `auth.agree_terms`, `auth.terms_of_service`, `auth.privacy_policy`, `auth.login_failed`, `auth.register_failed`, `auth.*_placeholder`, `auth.institution_types.*` | Full auth form coverage |
| `upload.add_more`, `upload.button_multi`, `upload.button_running`, `upload.uploading`, `upload.upload_complete`, `upload.image_ocr_warning_*`, `upload.unsupported_format`, `upload.file_too_large`, `upload.upload_failed`, `upload.pipeline_note` | All upload UX states |
| `pipeline.chunking`, `pipeline.embedding`, `pipeline.analysis_*`, `pipeline.review_metrics`, `pipeline.overall_progress`, `pipeline.pipeline_info`, `pipeline.stage`, `pipeline.step_elapsed`, `pipeline.est_remaining`, `pipeline.retry`, `pipeline.contact_support`, `pipeline.error_*`, `pipeline.could_not_load_status`, `pipeline.chunks_classified`, `pipeline.esg_relevant`, `pipeline.not_relevant`, `pipeline.processing` | Full pipeline page coverage |
| `metrics.unit`, `metrics.pillar`, `metrics.source`, `metrics.source_evidence`, `metrics.approved`, `metrics.rejected`, `metrics.edit`, `metrics.saving`, `metrics.approve_all`, `metrics.reject_all`, `metrics.no_match`, `metrics.no_evidence`, `metrics.select_to_view`, `metrics.total_extracted`, `metrics.needs_review`, `metrics.low_confidence_warning`, `metrics.reason_for_edit`, `metrics.note_placeholder`, `metrics.fra_code`, `metrics.sasb_code`, `metrics.required_for`, `metrics.indicators_reviewed`, `metrics.need_review_count*`, `metrics.search_placeholder` | Full metrics review page coverage |
| `report.*` (all new sub-keys) | Full ReportView page coverage including tabs, gap analysis, GRI index |
| `status.*` | Canonical metric and report status labels |
| `tier.*` | ESG tier labels (Leading/Established/Developing/Laggard) |
| `dashboard.*` | Full dashboard coverage |
| `consultant.*` | Full Consultant Workspace coverage |
| `admin.*` | Full Admin Console coverage |
| `landing.*` | Full Landing page coverage (all hardcoded strings) |
| `theme.*` | Light/dark mode toggle labels |
| `language.*` | Language toggle labels |
| `time.*` | Relative time labels ("just now", "2m ago", etc.) |
| `errors.*` | Unified error messages including ErrorBoundary strings |
| `common.close`, `common.search`, `common.filter`, `common.all`, `common.none`, `common.yes`, `common.no`, `common.or`, `common.and`, `common.na`, `common.page`, `common.optional`, `common.required_field`, `common.coming_soon`, `common.new`, `common.edit`, `common.delete`, `common.download`, `common.upload`, `common.submit`, `common.send`, `common.open`, `common.view`, `common.refresh`, `common.copied`, `common.copy`, `common.share`, `common.export`, `common.import`, `common.settings`, `common.help`, `common.about` | Expanded common actions |

**Existing keys preserved:** All original `nav.*`, `page.*`, `auth.login`, `auth.register`, `auth.email`, `auth.password`, `auth.fullName`, `auth.submit_login`, `auth.submit_register`, `auth.already_have_account`, `auth.no_account`, `upload.title`, `upload.subtitle`, `upload.drop_hint`, `upload.browse`, `upload.button`, `upload.max_size`, `pipeline.queued`–`pipeline.failed`, `metrics.gri_code`–`metrics.empty`, `report.generate`, `report.download`, `report.status_pending`, `report.status_ready`, `framework.*`, `pillar.E/S/G`, `common.loading`–`common.back`.
