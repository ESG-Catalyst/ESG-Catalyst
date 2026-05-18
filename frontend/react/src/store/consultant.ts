import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface ClientContext {
  companyId: string
  companyName: string
  institutionType: string
}

interface ConsultantState {
  activeClient: ClientContext | null
  setActiveClient: (client: ClientContext) => void
  clearActiveClient: () => void
}

export const useConsultantStore = create<ConsultantState>()(
  persist(
    (set) => ({
      activeClient: null,
      setActiveClient: (client) => set({ activeClient: client }),
      clearActiveClient: () => set({ activeClient: null }),
    }),
    { name: 'esg-consultant-ctx' },
  ),
)
