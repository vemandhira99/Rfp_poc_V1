/**
 * rfpStore.ts
 * -----------
 * Zustand-based data cache for RFP dashboard data.
 * Prevents dashboard from flashing 0 on navigation.
 * Data is fetched once and cached; background refresh updates silently.
 */
import { create } from 'zustand'

export type DashboardStats = {
  activeRFPs: number
  pendingReview: number
  totalValue: number
  approvedCount: number
  rejectedCount: number
}

export type RFPItem = {
  id: number
  title: string
  client: string
  deadline: string
  value: string
  status: string          // internal status
  displayStatus: string   // user-facing label
  risk: 'low' | 'medium' | 'high' | 'critical'
  effort: string
  summary?: any
  client_name?: string
  current_status?: string
  summary_json?: string
}

type RFPStore = {
  stats: DashboardStats | null
  rfps: RFPItem[]
  saRfps: any[]
  isInitialized: boolean
  isInitialLoading: boolean
  isRefetching: boolean
  lastFetched: number | null
  setStats: (stats: DashboardStats) => void
  setRfps: (rfps: RFPItem[]) => void
  setSaRfps: (saRfps: any[]) => void
  setLoading: (loading: boolean) => void
  setRefetching: (refetching: boolean) => void
  setInitialized: () => void
  setLastFetched: () => void
  clear: () => void
}

export const useRFPStore = create<RFPStore>((set) => ({
  stats: null,
  rfps: [],
  saRfps: [],
  isInitialized: false,
  isInitialLoading: false,
  isRefetching: false,
  lastFetched: null,
  setStats: (stats) => set({ stats }),
  setRfps: (rfps) => set({ rfps }),
  setSaRfps: (saRfps) => set({ saRfps }),
  setLoading: (isInitialLoading) => set({ isInitialLoading }),
  setRefetching: (isRefetching) => set({ isRefetching }),
  setInitialized: () => set({ isInitialized: true }),
  setLastFetched: () => set({ lastFetched: Date.now() }),
  clear: () => set({ stats: null, rfps: [], isInitialized: false, lastFetched: null }),
}))
