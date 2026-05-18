import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface UIState {
  sidebarCollapsed: boolean
  language: 'en' | 'ar'
  toggleSidebar: () => void
  setLanguage: (lang: 'en' | 'ar') => void
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      language: 'en',
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setLanguage: (language) => set({ language }),
    }),
    { name: 'esg-ui-prefs' },
  ),
)
