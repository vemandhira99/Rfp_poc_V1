'use client'

import { useState, useEffect, Suspense, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { Folder, Timer, ShieldCheck, User, Award, Search, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getStatusInfo, formatDeadline, formatClient } from '@/lib/statusUtils'
import { Badge } from '@/components/ui/badge'
import { useRFPStore } from '@/store/rfpStore'

function StatusBadge({ status, documentQuality }: { status: string; documentQuality?: string | null }) {
  const { label, badgeClass, isPulsing } = getStatusInfo(status, documentQuality)
  return (
    <span className={cn('px-2 py-0.5 rounded-full text-[10px] font-bold uppercase border', badgeClass, isPulsing && 'animate-pulse')}>
      {label}
    </span>
  )
}

function AssignedRfpsContent() {
  const router = useRouter()
  const { saRfps, setSaRfps, isInitialized, isInitialLoading, setLoading, isRefetching, setRefetching, setInitialized, setLastFetched, lastFetched } = useRFPStore()
  const [search, setSearch] = useState('')

  const load = useCallback(async (isBackground = false) => {
    if (isBackground) setRefetching(true)
    else if (!isInitialized) setLoading(true)
    
    try {
      const { fetchApi } = await import('@/lib/api')
      const data = await fetchApi('/rfps/assigned-to-me')
      const mapped = data.map((r: any) => ({
        ...r,
        clientDisplay: formatClient(r.client_name),
        deadlineDisplay: formatDeadline(r.deadline),
        daysLeft: r.deadline ? Math.ceil((new Date(r.deadline).getTime() - Date.now()) / 864e5) : null,
        assignedByName: r.assigned_by_name || 'Project Manager',
        complexity: r.complexity_score > 7 ? 'High' : r.complexity_score > 4 ? 'Medium' : 'Low',
        complexityLevel: r.complexity_score > 7 ? 3 : r.complexity_score > 4 ? 2 : 1,
        status: r.current_status,
      }))
      setSaRfps(mapped)
      setInitialized()
      setLastFetched()
    } catch (err) {
      console.error('Failed to load assigned RFPs', err)
    } finally {
      setLoading(false)
      setRefetching(false)
    }
  }, [setSaRfps, setInitialized, setLastFetched, setLoading, setRefetching, isInitialized])

  useEffect(() => {
    const isCacheFresh = lastFetched && (Date.now() - lastFetched < 120000)
    if (isInitialized && isCacheFresh) {
       load(true)
    } else {
       load()
    }
    const iv = setInterval(() => load(true), 30000)
    return () => clearInterval(iv)
  }, [load, isInitialized, lastFetched])

  const showSkeleton = isInitialLoading && !isInitialized
  const rfps = saRfps

  const filtered = rfps.filter(r =>
    r.title?.toLowerCase().includes(search.toLowerCase()) ||
    r.clientDisplay?.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="space-y-6 pb-8 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-xl lg:text-2xl font-bold tracking-tight text-zinc-900">Assigned Workspace</h1>
          <p className="text-xs text-zinc-500 mt-1 font-medium">RFPs assigned for your technical response and architecture design</p>
        </div>
        <div className="flex items-center gap-6">
          {isRefetching && (
             <span className="flex items-center gap-1.5 text-[10px] font-bold text-zinc-400 uppercase tracking-widest">
               <RefreshCw className="w-3 h-3 animate-spin" /> Syncing
             </span>
          )}
          <div className="flex flex-col items-end">
            <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Total Assigned</span>
            <span className="text-xl font-black text-zinc-900 leading-none mt-1">{rfps.length}</span>
          </div>
        </div>
      </div>

      {/* Filter & Search */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 group">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-400 group-focus-within:text-zinc-900 transition-colors" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by RFP title or client name..."
            className="w-full h-10 pl-9 pr-4 text-xs font-medium rounded-lg border border-zinc-200 bg-white outline-none focus:border-zinc-400 focus:ring-4 focus:ring-zinc-900/5 transition-all"
          />
        </div>
      </div>

      {/* RFP Cards */}
      <div className="grid grid-cols-1 gap-4">
        {showSkeleton ? (
          Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="premium-card h-32 animate-pulse bg-white/50" />
          ))
        ) : filtered.length === 0 ? (
          <div className="premium-card py-16 text-center bg-white/50 border-dashed">
            <div className="w-12 h-12 bg-zinc-50 rounded-2xl flex items-center justify-center mx-auto mb-4 border border-zinc-100">
              <Folder className="w-5 h-5 text-zinc-300" />
            </div>
            <h3 className="text-sm font-bold text-zinc-900">
              {search ? 'No matches found' : 'No assigned tasks'}
            </h3>
            <p className="text-xs text-zinc-400 mt-1.5 font-medium">
              {search ? 'Try adjusting your search terms.' : 'Check back later or contact your PM for new assignments.'}
            </p>
          </div>
        ) : (
          filtered.map(rfp => (
            <div key={rfp.id} className="premium-card premium-card-hover group bg-white overflow-hidden">
              <div className="flex items-stretch min-h-[120px]">
                {/* Status Indicator Bar */}
                <div className={cn("w-1.5", 
                  rfp.status.includes('error') ? 'bg-rose-500' : 
                  rfp.status.includes('ready') ? 'bg-indigo-500' : 
                  rfp.status.includes('final') ? 'bg-emerald-500' : 'bg-zinc-200'
                )} />
                
                <div className="flex-1 p-5 flex flex-col justify-between">
                  <div>
                    <div className="flex items-center gap-3 mb-2">
                      <StatusBadge status={rfp.status} documentQuality={rfp.document_quality} />
                      <span className="text-[10px] font-black text-zinc-400 uppercase tracking-widest leading-none">{rfp.clientDisplay}</span>
                    </div>
                    <h2 className="text-[15px] font-bold text-zinc-900 tracking-tight leading-tight group-hover:text-indigo-600 transition-colors line-clamp-1">
                      {rfp.title}
                    </h2>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-6 mt-4">
                    <div className="space-y-1.5">
                      <div className="flex items-center text-[9px] font-bold uppercase tracking-widest text-zinc-400 gap-1.5">
                        <Timer className="w-3 h-3" /> Deadline
                      </div>
                      <div className="flex flex-col">
                        <span className="text-xs font-bold text-zinc-900 leading-none">{rfp.deadlineDisplay}</span>
                        {rfp.daysLeft !== null && (
                          <span className={cn('text-[9px] font-bold mt-1 uppercase tracking-tighter', rfp.daysLeft <= 7 ? 'text-rose-500' : 'text-emerald-500')}>
                            {rfp.daysLeft > 0 ? `${rfp.daysLeft} days left` : 'Due now'}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="space-y-1.5">
                      <div className="flex items-center text-[9px] font-bold uppercase tracking-widest text-zinc-400 gap-1.5">
                        <ShieldCheck className="w-3 h-3" /> Complexity
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="flex gap-0.5">
                          {[1,2,3].map(i => (
                            <div key={i} className={cn('w-1 h-3 rounded-full', i <= rfp.complexityLevel ? 'bg-zinc-900' : 'bg-zinc-100')} />
                          ))}
                        </div>
                        <span className="text-xs font-bold text-zinc-900">{rfp.complexity}</span>
                      </div>
                    </div>

                    <div className="space-y-1.5">
                      <div className="flex items-center text-[9px] font-bold uppercase tracking-widest text-zinc-400 gap-1.5">
                        <User className="w-3 h-3" /> Assignee
                      </div>
                      <div className="text-xs font-bold text-zinc-900 truncate">{rfp.assignedByName}</div>
                    </div>

                    <div className="space-y-1.5">
                      <div className="flex items-center text-[9px] font-bold uppercase tracking-widest text-zinc-400 gap-1.5">
                        <Award className="w-3 h-3" /> Priority
                      </div>
                      <Badge variant="outline" className={cn("h-4 px-1.5 text-[9px] font-black uppercase tracking-tighter border-none", 
                        rfp.complexityLevel === 3 ? 'bg-rose-50 text-rose-600' : 
                        rfp.complexityLevel === 2 ? 'bg-amber-50 text-amber-600' : 'bg-zinc-100 text-zinc-600'
                      )}>
                        {rfp.complexityLevel === 3 ? 'High' : rfp.complexityLevel === 2 ? 'Medium' : 'Standard'}
                      </Badge>
                    </div>
                  </div>
                </div>

                {/* Open Workspace Button */}
                <button
                  onClick={() => router.push(`/dashboard/architect/workspace?id=${rfp.id}`)}
                  className="w-32 bg-zinc-50/50 border-l border-zinc-100 flex flex-col items-center justify-center gap-3 text-zinc-400 hover:text-zinc-900 hover:bg-zinc-100 transition-all active:scale-95 group/btn"
                >
                  <div className="w-10 h-10 rounded-2xl bg-white border border-zinc-200 flex items-center justify-center shadow-sm group-hover/btn:border-zinc-400 group-hover/btn:scale-110 transition-all">
                    <Folder className="w-5 h-5" />
                  </div>
                  <span className="text-[10px] font-black uppercase tracking-widest text-zinc-400 group-hover/btn:text-zinc-900 transition-colors">Workspace</span>
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export default function ArchitectDashboard() {
  return (
    <Suspense fallback={<div className="animate-pulse space-y-3"><div className="h-8 w-48 bg-zinc-100 rounded" />{[1,2,3].map(i=><div key={i} className="h-28 bg-zinc-100 rounded-xl"/>)}</div>}>
      <AssignedRfpsContent />
    </Suspense>
  )
}
