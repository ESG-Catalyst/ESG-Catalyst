import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type Theme = 'dark' | 'light'

interface UIState {
  sidebarCollapsed: boolean
  language: 'en' | 'ar'
  theme: Theme
  toggleSidebar: () => void
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

const initialTheme = getInitialTheme()
applyTheme(initialTheme)

export const useUIStore = create<UIState>()(
  persist(
    (set, get) => ({
      sidebarCollapsed: false,
      language: 'en',
      theme: initialTheme,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setLanguage: (language) => set({ language }),
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
      },
    },
  ),
)
