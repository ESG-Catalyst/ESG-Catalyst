# UI Polish — Account, Dashboard & Portal Pages

Agent 4 delivery. Five pages reworked: Login, Register, Dashboard, ConsultantWorkspace, Admin.

---

## Per-page changes

### Login (`src/pages/auth/Login.tsx`)

**What changed (presentation only):**
- Replaced `style={{ background }}` on the root div with `bg-bg` semantic class.
- Added `motion.div` fade-in (opacity 0→1, y 12→0, 350ms easeOut) around the whole form panel.
- Added a small brand stamp (teal icon + "ESG Catalyst" label) above the heading.
- Password field now has a show/hide toggle (`Eye`/`EyeOff`) via local `showPassword` state.
- All inputs use `rounded-lg` (was `rounded`), `py-2.5` (was `py-2`), `hover:border-border` idle state, and a proper `focus-visible:ring-2 ring-primary` focus ring — never `outline-none` alone.
- Submit button uses Tailwind semantic classes `bg-primary hover:bg-primary-hover text-white` instead of `style={{ background: 'var(--color-primary)', color: '#fff' }}` plus inline mouse-enter/leave handlers.
- `<Field>` now receives `id` prop and renders `<label htmlFor={id}>` — properly tied to each input.
- Error paragraph gains `role="alert"` and `id` for `aria-describedby` on the input.
- Server error banner gains `role="alert"` and a motion scale-in.
- "Forgot password?" styled as `text-xs` for visual hierarchy.
- Footer Terms/Privacy note added below the form.
- RTL: all physical `pl/pr/ml/mr` replaced with logical `ps/pe/ms/me`. Submit icon uses `aria-hidden`.

**Data / form wiring: untouched.** `useForm + zodResolver`, `login()` API call, `setAuth()`, `navigate('/dashboard')`, `serverError` state — all identical.

---

### Register (`src/pages/auth/Register.tsx`)

**What changed (presentation only):**
- Same motion fade-in + brand stamp as Login.
- Two password fields now have independent show/hide toggles.
- **Password strength meter** added below the password field: four horizontal segments that fill as the user types (Weak / Fair / Good / Strong), color-coded to match the semantic palette. Uses local `watch('password')` — no schema change, no new state beyond `showPassword`/`showConfirm`.
- Fields grouped visually with `SectionLabel` dividers ("Account details" / "Institution").
- Select styled with `appearance-none` and consistent `rounded-lg` treatment.
- `<Field>` receives `id` + `htmlFor` like Login.
- Checkbox terms error is `role="alert"` and correctly `ms-6` (logical) instead of physical.
- Submit button uses Tailwind semantic classes.
- RTL-correct throughout.

**Data / form wiring: untouched.** Same `z.object` schema, `.refine()` confirm-password check, `registerUser()` call, `setAuth()`, `navigate('/dashboard')`.

---

### Dashboard (`src/pages/Dashboard.tsx`)

**What changed (presentation only):**
- Greeting now includes the email handle (`emailHandle(email)` from auth store): "Good morning, ahmed.youssef" — previously "Good morning" with blank user suffix.
- `ScoreCard` gains a row of three `StatChip` components below the gauge (Approved / Extracted / Missing counts with color coding). Tier badge gains a `TrendingUp` icon.
- `CoverageCard` footer line now has an `Activity` icon and bolder disclosed count.
- `ActivityFeed` items now use a small colored icon-tile (6×6 rounded square) instead of a bare icon, for visual grouping. Empty state gets an icon + centered layout.
- `QuickActionCard` wraps in `motion.div` with `whileHover={{ y: -2 }}`. Primary "Upload" card gets `variant="primary"` so its icon tile is teal-filled. Submit button inside uses Tailwind `bg-primary hover:bg-primary-hover` not inline handlers.
- `MetricsSummaryTable` gets a proper header row within the card (title + "View all" link), table uses `text-start` / `scope="col"` for a11y.
- `LoadingSkeleton` extracted to its own component with `aria-busy="true"`.
- `EmptyState` wraps in `motion.div` fade-in; icon container is `rounded-2xl`.
- All `Card` wrappers now use `rounded-xl bg-surface border-border` via Tailwind classes.
- All `onMouseEnter/Leave` style-swapping replaced with Tailwind hover classes.
- RTL-safe throughout (logical utilities).

**Data / form wiring: untouched.** All four `useQuery` calls, `useMutation(generateReport)`, `queryClient.invalidateQueries`, `navigate`, `emailHandle` import — unchanged.

---

### ConsultantWorkspace (`src/pages/ConsultantWorkspace.tsx`)

**What changed (presentation only):**
- **Search bar added** above the client grid (filters by name/type in-component, no API call, no new store field — purely local `search` state + array filter).
- `ClientCard` wrapped in `motion.div whileHover={{ y: -2 }}`. Meta row now has a top border separator. Tier badge gains a border. Action buttons use Tailwind hover classes.
- `AddClientModal` gains `motion.div` scale-in animation via `AnimatePresence`, `autoFocus` on first input, and an improved success state (circular check icon).
- `ComparisonPanel` dropdown wrapped in `AnimatePresence` motion fade, uses `aria-haspopup="listbox"` + `aria-expanded`, inner options use `role="option" aria-selected`.
- Comparison table moved inside a `rounded-lg border border-border` wrapper.
- `ActivityFeed` section title uses `SectionLabel` styling.
- `AccessDenied` icon container uses `bg-danger/10 border-danger/20 rounded-2xl`.
- Export CSV button label shortened to "Export CSV".
- Empty search result state added (no results illustration + message).
- All `style={{ background }}` inline colour swaps replaced with Tailwind classes.
- RTL-safe: `text-start`, `start-/end-`, `ms-/me-`, `ps-/pe-` used throughout.

**Data / role wiring: untouched.** `useConsultantStore`, `useAuthStore`, role guard (`!== 'consultant' && !== 'admin'`), `navigate('/dashboard')`, `downloadComparisonCSV`, all mock-data references — unchanged.

---

### Admin (`src/pages/Admin.tsx`)

**What changed (presentation only):**
- Page header icon changed from plain `Shield` to a `Shield` in a tinted `bg-danger/12` tile, matching the teal brand-icon pattern.
- Refresh button gains a border and `isFetching`-driven spin on the icon (replaces the always-static icon).
- `StatsBar` uses `text-[10px] font-bold uppercase tracking-widest` for role labels, `font-mono` for counts.
- Stats-bar skeleton added while loading (four pulse boxes).
- `RoleSelector` dropdown wrapped in `AnimatePresence` motion (scale + opacity). Chevron animates on open. `aria-haspopup="listbox"` + `aria-expanded` + inner `role="option" aria-selected` added.
- `UserAvatar` component extracted: computes two-letter initials from email local-part (same logic as sidebar). Self-row gets primary background; others get surface-raised.
- Table rows get `hover:bg-surface-raised/40` hover state. Self-row gets `ring-1 ring-inset ring-primary/20` so the logged-in user's row has a subtle teal highlight.
- "you" badge gets a pill style (`rounded-full bg-surface-raised border`).
- Skeleton rows extracted to `SkeletonRow` component.
- Empty state gains a centred icon.
- User count footer line added below table ("Showing N of M users").
- Search box uses the same `ps-9` icon-inside pattern as ConsultantWorkspace.
- Admin instructions panel uses `Terminal` icon instead of `Shield`.
- All inline `onMouseEnter/Leave` style handlers replaced with Tailwind hover classes.
- RTL: `text-start`, `end-0`, `ms-` throughout.

**Data / mutation wiring: untouched.** `listUsers()`, `updateUserRole()`, `useQuery(['admin-users'])`, `useMutation`, `queryClient.setQueryData`, `selfId`, `search`/`roleFilter` state, `retry: 1` — all unchanged.

---

## Shared-component prop gaps (flag for Agent 1)

| Component | Current props | Gap observed |
|-----------|--------------|--------------|
| `ScoreGauge` | `scores`, `overall`, `size` | No `aria-label` on the outer container — if Agent 1 adds one, callers can pass `label` prop. Currently the inner SVGs have `aria-label` on individual rings which is acceptable. |
| `FrameworkCoverageBar` | `framework`, `covered`, `total`, `className` | No gap; used as-is. |
| `StatusPill` | `status`, `className` | No gap; used as-is. |

---

## Reconciliation notes for orchestrator

1. **`cn()` usage** — all five files now import `cn` from `@/lib/utils`. Other agents should also use it instead of `clsx()` directly.
2. **`bg-primary hover:bg-primary-hover text-white`** — replaced all inline `onMouseEnter/Leave` style-swaps on primary buttons. Other pages may still have the old pattern; reconciler should normalise.
3. **`AnimatePresence` wrapping modals/dropdowns** — used in ConsultantWorkspace and Admin. The pattern (`AnimatePresence > motion.div initial/animate/exit`) is consistent with PipelineProgress / Results existing code.
4. **Tailwind `rounded-xl`** — used consistently for card containers in this set; existing other pages use `rounded-lg`. No conflict, just a slight visual difference agents should align on.
5. **`focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2`** on submit buttons, `focus-visible:ring-2 focus-visible:ring-primary` on all inputs — this pattern was not present before. Orchestrator should check other pages (Upload, Results, etc.) for consistency.

---

## Next priorities

1. Normalise `bg-primary hover:bg-primary-hover text-white` on all button-like elements across ALL pages (Upload, PipelineProgress, Results, ReportView) — currently they still use inline style swap.
2. Add `focus-visible:ring-2` to all interactive elements site-wide (currently only the five pages in this set have it).
3. Dashboard `ScoreCard` currently recalculates scores as `avgConf * 100` — a known limitation noted in CLAUDE.md (v2: wire `score_metric`). No change made here; this is business logic.
4. ConsultantWorkspace uses mock data (`MOCK_CLIENTS`). When API client portfolio endpoints are added, swap the constant for a `useQuery` call.
5. Admin: consider adding `@tanstack/react-query` `placeholderData: keepPreviousData` to preserve the user list during refetch so the table doesn't flash skeletons on refresh.
