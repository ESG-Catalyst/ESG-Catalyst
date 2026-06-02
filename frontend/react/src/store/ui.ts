import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type Theme = 'dark' | 'light'

interface UIState {
  sidebarCollapsed: boolean
  /** Whether the mobile sidebar drawer is open (separate from collapsed state) */
  mobileSidebarOpen: boolean
  language: 'en' | 'ar'
  theme: Theme
  toggleSidebar: () => void
  setMobileSidebarOpen: (open: boolean) => void
  setLanguage: (lang: 'en' | 'ar') => void
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
}

const PERSIST_KEY = 'esg-ui-prefs'

function readPersistedTheme(): Theme | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = localStorage.getItem(PERSIST_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as { state?: { theme?: unknown } }
    const t = parsed?.state?.theme
    return t === 'light' || t === 'dark' ? t : null
  } catch {
    return null
  }
}

function readPersistedLang(): 'en' | 'ar' | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = localStorage.getItem(PERSIST_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as { state?: { language?: unknown } }
    const l = parsed?.state?.language
    return l === 'en' || l === 'ar' ? l : null
  } catch {
    return null
  }
}

function systemPrefersLight(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  return window.matchMedia('(prefers-color-scheme: light)').matches
}

function getInitialTheme(): Theme {
  return readPersistedTheme() ?? (systemPrefersLight() ? 'light' : 'dark')
}

function applyTheme(theme: Theme) {
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.theme = theme
  }
}

/** Applies `dir` and `lang` attributes to `<html>` for full RTL/LTR switching. */
export function applyLang(lang: 'en' | 'ar') {
  if (typeof document === 'undefined') return
  const html = document.documentElement
  html.lang = lang
  html.dir = lang === 'ar' ? 'rtl' : 'ltr'
  // Apply Arabic font to body so all text flips without per-component overrides
  document.body.style.fontFamily = lang === 'ar' ? 'var(--font-arabic)' : ''
}

const initialTheme = getInitialTheme()
const initialLang: 'en' | 'ar' = readPersistedLang() ?? 'en'

// Apply both eagerly before first render to avoid FOUC
applyTheme(initialTheme)
applyLang(initialLang)

export const useUIStore = create<UIState>()(
  persist(
    (set, get) => ({
      sidebarCollapsed: false,
      mobileSidebarOpen: false,
      language: initialLang,
      theme: initialTheme,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setMobileSidebarOpen: (open) => set({ mobileSidebarOpen: open }),
      setLanguage: (language) => {
        applyLang(language)
        set({ language })
      },
      setTheme: (theme) => {
        applyTheme(theme)
        set({ theme })
      },
      toggleTheme: () => {
        const next: Theme = get().theme === 'dark' ? 'light' : 'dark'
        applyTheme(next)
        set({ theme: next })
      },
    }),
    {
      name: PERSIST_KEY,
      onRehydrateStorage: () => (state) => {
        if (state?.theme) applyTheme(state.theme)
        if (state?.language) applyLang(state.language)
      },
    },
  ),
)
