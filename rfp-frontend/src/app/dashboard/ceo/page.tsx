'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { Upload, TrendingUp, Clock, ArrowUpRight, RefreshCw, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { UploadRfpModal } from '@/components/rfp/UploadRfpModal'
import { getStatusInfo, getStatusLabel, formatValue, formatClient, formatDeadline } from '@/lib/statusUtils'
import { useRFPStore } from '@/store/rfpStore'

// ─── Status Badge ────────────────────────────────────────────────────────────
function StatusBadge({ status, documentQuality }: { status: string; documentQuality?: string | null }) {
  const { label, badgeClass, isPulsing } = getStatusInfo(status, documentQuality)
  return (
    <Badge variant="outline" className={cn('text-[11px] font-semibold px-2 py-0.5 whitespace-nowrap', badgeClass, isPulsing && 'animate-pulse')}>
      {label}
    </Badge>
  )
}

// ─── Truncated cell with tooltip ─────────────────────────────────────────────
function TruncCell({ text, lines = 1, className = '' }: { text: string; lines?: number; className?: string }) {
  return (
    <span
      title={text}
      className={cn(
        'block overflow-hidden text-ellipsis',
        lines === 1 ? 'whitespace-nowrap' : 'line-clamp-2',
        className
      )}
    >
      {text}
    </span>
  )
}

// ─── Short effort label ───────────────────────────────────────────────────────
function formatEffortShort(effort: string | undefined | null): string | null {
  if (!effort || effort === 'TBD' || effort.trim() === '') return null
  // Already short (≤ 20 chars)
  if (effort.length <= 20) return effort
  // Extract duration-like prefix: "2 years", "18 months", "High", etc.
  const durationMatch = effort.match(/^(High|Medium|Low|\d+[\s‑–-]+(?:year|month|week|day)[s]?)/i)
  if (durationMatch) return durationMatch[1]
  // Fallback: first 3 words
  const words = effort.trim().split(/\s+/).slice(0, 3).join(' ')
  return words.length < effort.length ? words + '…' : words
}

// ─── Progress Bar for active drafts ──────────────────────────────────────────
function DraftProgress({ rfpId, status }: { rfpId: number; status: string }) {
  const [progress, setProgress] = useState(0)
  const [isCancelling, setIsCancelling] = useState(false)
  const isDrafting = status === 'generating_draft' || status === 'in_drafting'

  useEffect(() => {
    if (!isDrafting) return
    const poll = async () => {
      try {
        const { fetchApi } = await import('@/lib/api')
        const data = await fetchApi(`/rfps/${rfpId}/generation-progress`)
        const pct = data.total > 0 ? Math.round((data.current / data.total) * 100) : 0
        setProgress(pct)
      } catch { setProgress(p => Math.min(p + 0.5, 95)) }
    }
    poll()
    const iv = setInterval(poll, 6000)
    return () => clearInterval(iv)
  }, [rfpId, isDrafting])

  if (!isDrafting) return null

  return (
    <div className="w-full mt-1.5">
      <div className="flex justify-between items-center mb-0.5">
        <span className="text-[10px] font-bold text-purple-600 animate-pulse uppercase tracking-tight">Drafting</span>
        <div className="flex items-center gap-1">
          <span className="text-[10px] font-medium text-zinc-500">{progress}%</span>
          <button
            onClick={async (e) => {
              e.stopPropagation()
              if (isCancelling) return
              setIsCancelling(true)
              try {
                const { fetchApi } = await import('@/lib/api')
                await fetchApi(`/rfps/${rfpId}/cancel-generation`, { method: 'POST' })
              } finally { setIsCancelling(false) }
            }}
            className="text-rose-400 hover:text-rose-600 p-0.5 rounded transition-colors"
            title="Cancel draft generation"
          >
            <svg className="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
      <div className="w-full bg-zinc-100 rounded-full h-1 overflow-hidden">
        <div className="bg-purple-500 h-full rounded-full transition-all duration-700" style={{ width: `${progress}%` }} />
      </div>
    </div>
  )
}

// ─── Skeleton Row ─────────────────────────────────────────────────────────────
function SkeletonRow() {
  return (
    <tr className="border-b border-zinc-100">
      {[60, 20, 10, 10, 10, 8, 10].map((w, i) => (
        <td key={i} className="py-3 px-3">
          <div className="h-3.5 rounded bg-zinc-100 animate-pulse" style={{ width: `${Math.min(w * 1.2, 100)}%` }} />
        </td>
      ))}
    </tr>
  )
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────
export default function CEODashboard() {
  const router = useRouter()
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false)
  const [activeFilter, setActiveFilter] = useState<'all' | 'pending'>('all')
  const [searchTerm, setSearchTerm] = useState('')
  const { stats, rfps, isInitialized, isInitialLoading, isRefetching, setStats, setRfps, setLoading, setRefetching, setInitialized, setLastFetched, lastFetched } = useRFPStore()

  const loadData = useCallback(async (isBackground = false) => {
    if (isBackground) setRefetching(true)
    else if (!isInitialized) setLoading(true)
    
    try {
      const { fetchApi } = await import('@/lib/api')
      const [statsData, rfpsData] = await Promise.all([
        fetchApi('/rfps/dashboard-summary'),
        fetchApi('/rfps/')
      ])

      setStats({
        activeRFPs: statsData.total ?? 0,
        pendingReview: statsData.under_review ?? 0,
        totalValue: statsData.total_value ?? 0,
        approvedCount: statsData.approved ?? 0,
        rejectedCount: statsData.rejected ?? 0,
      })

      const mapped = (rfpsData as any[]).map((r: any) => {
        let summary: any = null
        try { if (r.summary_json) summary = JSON.parse(r.summary_json) } catch { }
        const rawEffort = summary?.effort_estimation || ''
        return {
          id: r.id,
          title: r.title || 'Untitled RFP',
          client: formatClient(summary?.client_name || r.client_name),
          deadline: formatDeadline(summary?.deadline || r.deadline),
          value: formatValue(summary?.value || summary?.contract_value),
          status: r.current_status || 'uploaded',
          documentQuality: r.document_quality,
          displayStatus: getStatusLabel(r.current_status),
          risk: (summary?.risks?.length > 2 ? 'high' : summary?.risks?.length > 0 ? 'medium' : 'low') as any,
          effortShort: formatEffortShort(rawEffort),
          effort: rawEffort,
          summary,
        }
      })
      setRfps(mapped)
      setInitialized()
      setLastFetched()
    } catch (err) {
      console.error('Dashboard load error:', err)
    } finally {
      setLoading(false)
      setRefetching(false)
    }
  }, [setStats, setRfps, setInitialized, setLastFetched, isInitialized, setLoading, setRefetching])

  useEffect(() => {
    // If we have fresh cached data (last 2 mins), skip initial load but refresh background
    const isCacheFresh = lastFetched && (Date.now() - lastFetched < 120000)
    if (isInitialized && isCacheFresh) {
       loadData(true)
    } else {
       loadData()
    }
    
    const iv = setInterval(() => loadData(true), 30000)
    return () => clearInterval(iv)
  }, [loadData, isInitialized, lastFetched])

  const showSkeleton = isInitialLoading && !isInitialized

  const filtered = rfps.filter(r => {
    const q = searchTerm.toLowerCase()
    const matchSearch = r.title.toLowerCase().includes(q) || r.client.toLowerCase().includes(q)
    if (activeFilter === 'pending') {
      return matchSearch && ['pending-review', 'summary_generated', 'under_review', 'awaiting_ceo_decision'].includes(r.status)
    }
    return matchSearch
  })

  const statCards = [
    { id: 'all', label: 'Active RFPs', value: stats?.activeRFPs ?? 0, icon: TrendingUp, color: 'text-blue-600', bg: 'bg-blue-50' },
    { id: 'pending', label: 'Pending Review', value: stats?.pendingReview ?? 0, icon: Clock, color: 'text-amber-600', bg: 'bg-amber-50' },
  ]

  return (
    <div className="space-y-6 pb-8 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-zinc-900 lg:text-2xl">RFP Dashboard</h1>
          <p className="text-xs text-zinc-500 mt-0.5 font-medium">Manage and review all active proposals</p>
        </div>
        <div className="flex items-center gap-3">
          {isRefetching && (
            <span className="flex items-center gap-1.5 text-[10px] font-bold text-zinc-400 uppercase tracking-widest">
              <RefreshCw className="w-3 h-3 animate-spin" /> Syncing
            </span>
          )}
          <Button
            size="sm"
            className="h-9 bg-zinc-900 hover:bg-zinc-800 text-white text-xs font-bold px-4 rounded-lg shadow-sm transition-all active:scale-95"
            onClick={() => setIsUploadModalOpen(true)}
          >
            <Upload className="w-3.5 h-3.5 mr-2" />
            New RFP
          </Button>
        </div>
      </div>

      <UploadRfpModal isOpen={isUploadModalOpen} onClose={() => { setIsUploadModalOpen(false); loadData(true) }} />

      {/* Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 lg:gap-5">
        {statCards.map(card => {
          const Icon = card.icon
          const isActive = activeFilter === card.id
          return (
            <div
              key={card.id}
              onClick={() => setActiveFilter(card.id as any)}
              className={cn(
                'premium-card p-4 cursor-pointer group',
                isActive ? 'ring-2 ring-zinc-900 ring-offset-2 border-transparent' : 'premium-card-hover'
              )}
            >
              <div className="flex items-center gap-4">
                <div className={cn('p-2.5 rounded-lg transition-all duration-300 group-hover:scale-110', isActive ? 'bg-zinc-900 text-white' : card.bg)}>
                  <Icon className={cn('w-5 h-5', isActive ? 'text-white' : card.color)} />
                </div>
                <div>
                  <p className="text-2xl font-black text-zinc-900 leading-none tracking-tight">
                    {showSkeleton ? <span className="w-8 h-6 bg-zinc-100 animate-pulse rounded inline-block" /> : card.value}
                  </p>
                  <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest mt-1.5">{card.label}</p>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* RFP Table */}
      <div className="premium-card overflow-hidden">
        <div className="px-5 py-3.5 border-b border-zinc-100 flex items-center justify-between gap-4 bg-zinc-50/30">
          <h2 className="text-[11px] font-bold text-zinc-400 uppercase tracking-widest">Active Proposals</h2>
          <div className="flex items-center gap-2">
            <div className="relative group">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-zinc-400 group-focus-within:text-zinc-900 transition-colors" />
              <input
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                placeholder="Search..."
                className="h-8 text-xs pl-8 pr-3 rounded-lg border border-zinc-200 bg-white outline-none focus:border-zinc-400 w-36 lg:w-48 transition-all"
              />
            </div>
            <select className="h-8 rounded-lg border border-zinc-200 bg-white px-2.5 text-[10px] font-bold uppercase tracking-wider text-zinc-600 outline-none hover:border-zinc-300 transition-colors cursor-pointer">
              <option>All Statuses</option>
              <option>Pending</option>
              <option>In Progress</option>
            </select>
          </div>
        </div>

        <div className="w-full overflow-x-auto">
          <table className="w-full min-w-[850px] text-left border-collapse" style={{ tableLayout: 'fixed' }}>
            <colgroup>
              <col style={{ width: '28%' }} />
              <col style={{ width: '18%' }} />
              <col style={{ width: '12%' }} />
              <col style={{ width: '12%' }} />
              <col style={{ width: '18%' }} />
              <col style={{ width: '12%' }} />
            </colgroup>
            <thead>
              <tr className="bg-zinc-50/50 border-b border-zinc-100">
                <th className="h-10 px-5 text-[10px] font-bold uppercase tracking-widest text-zinc-400">Title</th>
                <th className="h-10 px-3 text-[10px] font-bold uppercase tracking-widest text-zinc-400">Client</th>
                <th className="h-10 px-3 text-[10px] font-bold uppercase tracking-widest text-zinc-400">Deadline</th>
                <th className="h-10 px-3 text-[10px] font-bold uppercase tracking-widest text-zinc-400">Value</th>
                <th className="h-10 px-3 text-[10px] font-bold uppercase tracking-widest text-zinc-400">Status</th>
                <th className="h-10 px-5 text-right text-[10px] font-bold uppercase tracking-widest text-zinc-400">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-50">
              {showSkeleton ? (
                Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center">
                    <p className="text-sm font-medium text-zinc-400">No proposals found matching your criteria</p>
                  </td>
                </tr>
              ) : (
                filtered.map(rfp => (
                  <tr key={rfp.id} className="group hover:bg-zinc-50/40 transition-colors">
                    <td className="py-3.5 px-5 align-top">
                      <p className="text-[13px] font-bold text-zinc-900 leading-tight line-clamp-1 group-hover:text-blue-600 transition-colors" title={rfp.title}>
                        {rfp.title}
                      </p>
                      {rfp.effortShort && (
                        <div className="mt-1.5 flex items-center gap-1.5">
                          <span className="inline-flex items-center text-[9px] font-black uppercase text-zinc-500 bg-zinc-100 px-1.5 py-0.5 rounded tracking-tighter">
                            {rfp.effortShort}
                          </span>
                        </div>
                      )}
                    </td>
                    <td className="py-3.5 px-3 align-top">
                      <TruncCell text={rfp.client} className="text-xs font-semibold text-zinc-600" />
                    </td>
                    <td className="py-3.5 px-3 align-top">
                      <span className={cn("text-xs font-bold", rfp.deadline.includes('Days Left') ? 'text-rose-600' : 'text-zinc-900')}>
                        {rfp.deadline === 'Deadline TBD' ? '—' : rfp.deadline}
                      </span>
                    </td>
                    <td className="py-3.5 px-3 align-top">
                      <span className="text-xs font-bold text-zinc-900">{rfp.value}</span>
                    </td>
                    <td className="py-3.5 px-3 align-top">
                      <div className="flex flex-col gap-1.5">
                        <StatusBadge status={rfp.status} documentQuality={rfp.documentQuality} />
                        <DraftProgress rfpId={rfp.id} status={rfp.status} />
                      </div>
                    </td>
                    <td className="py-3.5 px-5 align-top text-right">
                      <div className="flex items-center justify-end gap-2">
                        {(rfp.status === 'error' || rfp.status === 'rate_limit_error') && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              import('@/lib/api').then(({ fetchApi }) => fetchApi(`/uploads/rfp/${rfp.id}/parse`, { method: 'POST' }).then(() => loadData(true)))
                            }}
                            className="text-[10px] font-black uppercase text-rose-600 hover:text-rose-700 transition-colors"
                          >
                            Resume
                          </button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 px-2.5 text-[11px] font-bold hover:bg-zinc-900 hover:text-white transition-all rounded-lg group/btn"
                          onClick={() => router.push(`/dashboard/ceo/rfp/${rfp.id}`)}
                        >
                          Details
                          <ArrowUpRight className="w-3 h-3 ml-1 transition-transform group-hover/btn:translate-x-0.5 group-hover/btn:-translate-y-0.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
