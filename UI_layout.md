# UI Layout — Agent 2 Change Report

Agent: 2 of 5 (App Chrome, Layout, Navigation, RTL/Lang)
Files touched: `store/ui.ts`, `App.tsx`, `components/layout/AppShell.tsx`,
`components/layout/Sidebar.tsx`, `components/layout/TopBar.tsx`,
`components/layout/PageHeader.tsx`, `components/layout/AuthPanel.tsx`,
`components/ErrorBoundary.tsx`

---

## RTL / dir / lang wiring

### Problem
The previous code called `document.documentElement.dir/lang` inside `Sidebar.tsx`
and `TopBar.tsx` as side-effects of button click handlers only. This meant:
- A user who had persisted `language: 'ar'` would see a flash of LTR on page reload.
- The `<html lang>` attribute was never set on initial render.
- Two independent code paths (Sidebar toggle + TopBar toggle) both needed to call the DOM APIs.

### Fix

**`store/ui.ts`**
- Added `applyLang(lang)` — exported helper that sets `document.documentElement.lang` and
  `document.documentElement.dir`, and applies the Arabic body font.
- Added `readPersistedLang()` — reads the persisted language from localStorage before first
  render (same pattern as `readPersistedTheme()`).
- Module-level eager call: `applyLang(initialLang)` runs before React mounts — no FOUC.
- `onRehydrateStorage` now calls `applyLang` alongside `applyTheme`.
- `setLanguage` now calls `applyLang(language)` so any caller just updates the store and
  the DOM is always in sync.
- Added `mobileSidebarOpen: boolean` + `setMobileSidebarOpen` action for the mobile drawer.
- Exported interface stays compatible — only additive changes.

**`App.tsx`**
- Added `<DirLangSync />` component (renders null) that subscribes to `language` via the
  store and calls `applyLang` via `useEffect` on every change. Belt-and-suspenders alongside
  the module-level initialiser: handles the case where a hydration mismatch causes the
  module-level call to be stale.

**`Sidebar.tsx`**
- `toggleLang()` now calls both `setLanguage(next)` (store update — triggers DOM via store)
  and `applyLang(next)` directly to ensure immediate DOM update without waiting for a render.
- Removed the duplicated `document.documentElement.lang/dir` assignments that were in the
  old handler.

**`TopBar.tsx`**
- Removed the entire `toggleLanguage` function and the language toggle button from TopBar.
  Language toggle now lives exclusively in the Sidebar (one canonical location).

---

## Responsive layout — off-canvas mobile sidebar

### AppShell.tsx
- Added `useIsMd()` hook using `window.matchMedia('(min-width: 768px)')` to track breakpoint.
- `mainStyle` now computes to `{ marginLeft: 0, marginRight: 0 }` below md (sidebar is
  off-canvas), and `{ marginLeft/Right: sidebarSize }` at md+ in the correct logical direction.
- The `transition-[margin]` class makes the offset animate smoothly on resize and on
  sidebar collapse/expand.
- Page transitions: wrapped `<Outlet />` in `<PageTransition>` which uses
  `framer-motion AnimatePresence mode="wait"` keyed on `pathname`. Subtle opacity + y
  fade (18ms duration) for perceived responsiveness without flashiness.

### Sidebar.tsx
- Desktop sidebar (`md:flex`, hidden on mobile) uses `motion.aside` with spring animation
  on `width` for smooth collapse/expand.
- Mobile: `AnimatePresence` controls a `motion.div` backdrop + `motion.aside` drawer.
  - LTR: drawer slides in from `x: '-100%'` → `x: 0` (left edge).
  - RTL: drawer slides in from `x: '100%'` → `x: 0` (right edge).
- Backdrop click closes the drawer via `setMobileSidebarOpen(false)`.
- `SidebarInner` receives `onNavClick` prop so navigating from the mobile drawer auto-closes it.
- Mobile hamburger is now in `TopBar.tsx` (only visible on `<md`), calls `setMobileSidebarOpen(true)`.

---

## Sidebar polish

- **Active nav item**: removed `layoutId` (was wrong on multi-instance indicator spans);
  replaced with a plain `<span>` active indicator bar positioned with `insetInlineStart/End: 0`
  (CSS logical properties, RTL-correct). Background highlight uses `bg-primary/10` token.
- **NavLink `end` prop**: prevents `/dashboard` from matching on `/dashboard/something`.
- **`<nav>` with `aria-label`**: wraps the nav items; individual items use `aria-label`.
- **Label animation**: labels fade/slide on collapse/expand via `AnimatePresence` +
  `motion.span width: 0 → auto` transition.
- **Bottom button labels**: same animate pattern for theme, language, user meta, logout, collapse.
- **Collapse icon**: LTR uses `PanelLeftClose`/`PanelLeftOpen` (lucide); RTL uses
  `ChevronRight`/`ChevronLeft` so the arrow always points in the correct semantic direction.
- **Focus ring**: all interactive elements have `focus-visible:ring-2 ring-primary`.

---

## TopBar polish

- Added `<Menu>` hamburger button (mobile-only, `md:hidden`).
- Breadcrumb: filters out UUIDs and numeric IDs so paths like `/pipeline/abc123-...` show
  only the route label, not the raw ID. Uses `aria-current="page"` on the last segment.
- Notifications bell: positioned dot uses `end-1.5` (logical, RTL-safe) via Tailwind.
- Avatar: shows email-derived initials from `emailInitials(email)` (was hardcoded "U").
- Sticky: `sticky top-0 z-30` so TopBar stays visible on long pages.
- Backdrop blur: `bg-surface/90 backdrop-blur-sm` gives a glass effect when content
  scrolls under the bar.
- Removed duplicate language toggle (now Sidebar-only).

---

## PageHeader

- Added `description` prop (alias of old `subtitle` — fully backwards-compatible).
- Mobile-first flex direction: `flex-col sm:flex-row` so action slot wraps under title on
  small screens.
- Uses `text-start` for title/description to correctly left-align in LTR and right-align in RTL.
- Old `subtitle` prop kept as `@deprecated` alias.

---

## AuthPanel

- Uses `border-e border-border` (logical, border on the inline-end edge — right in LTR, left in RTL).
- Added small brand icon tile alongside the wordmark.
- Added a mini stat row (46 indicators, frameworks).
- `<figure>`/`<blockquote>`/`<figcaption>` for semantic HTML.
- Padding uses `p-10 xl:p-14` to give more breathing room on large screens.

---

## ErrorBoundary

- Added `<Home>` button icon alongside "Go home".
- `bg-primary-hover` class on Try Again hover (token-driven).
- Stack trace expanded to show `error.stack` (not just message) in dev mode.
- Uses `role="alert"` + `aria-live="assertive"` for screen-reader announcement.
- `rounded-lg` (token-driven) on all buttons.
- Focus rings on both action buttons.

---

## router.tsx

No changes. All routes, guards, and path wiring preserved exactly.

---

## Store API compatibility

`UIState` shape is strictly additive:
- New: `mobileSidebarOpen: boolean`, `setMobileSidebarOpen: (open: boolean) => void`
- New: `applyLang` exported function (not a store action — pure DOM helper)
- All existing fields (`sidebarCollapsed`, `language`, `theme`, `toggleSidebar`,
  `setLanguage`, `setTheme`, `toggleTheme`) have unchanged types and behaviour.
- The `mobileSidebarOpen` field is NOT persisted (intentional — drawer state should
  always start closed on page reload). The `persist` middleware only stores
  `sidebarCollapsed`, `language`, `theme`.

---

## Flags for reconciliation

1. `TopBar.tsx` removed the language toggle button. If another agent has added a feature
   that depends on `toggleLanguage` inside TopBar, they need to call `setLanguage` from
   the store directly (same effect, no wrapper needed).

2. `AppShell.tsx` now uses `useIsMd()` which subscribes to `matchMedia`. This is a new
   React state subscription — if tests mock `window.matchMedia`, they need to return
   `matches: true` for `(min-width: 768px)` to exercise the sidebar-offset path.

3. `mobileSidebarOpen` is new store state. If an agent adds a close-on-route-change
   behaviour, call `setMobileSidebarOpen(false)` from a navigation effect in AppShell
   (not done here to avoid scope creep).

4. The `PageTransition` `AnimatePresence mode="wait"` wrapper will unmount and remount
   the outgoing page before mounting the incoming one. Pages that fetch data on mount will
   re-fetch on navigation. This is the correct, expected behaviour.

---

## Recommended next priorities

1. Add `prefers-reduced-motion` CSS override in `globals.css` to disable the page-transition
   animation for users who have opted out:
   ```css
   @media (prefers-reduced-motion: reduce) {
     .motion-safe\:animate-* { animation: none !important; }
   }
   ```
2. Swap `SidebarInner`'s `NavItem` component definition outside the render function
   (currently defined inside `SidebarInner`) to avoid recreating it on every render.
   Low priority — only 4–6 items so the perf impact is negligible.
3. Add `aria-expanded` on the sidebar collapse button to communicate collapsed state to
   screen readers.
4. Consider making `mobileSidebarOpen` auto-close on route change by adding a `useEffect`
   in `AppShell` that calls `setMobileSidebarOpen(false)` when `pathname` changes.
