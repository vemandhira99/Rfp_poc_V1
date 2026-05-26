'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { CheckCircle2, AlertCircle, XCircle, RefreshCw, User, Calendar, FileText, ArrowUpRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getStatusInfo, formatClient, formatDeadline } from '@/lib/statusUtils'
import { Badge } from '@/components/ui/badge'

function StatusBadge({ status, documentQuality }: { status: string; documentQuality?: string | null }) {
  const { label, badgeClass, isPulsing } = getStatusInfo(status, documentQuality)
  return (
    <span className={cn('px-2 py-0.5 rounded-full text-[10px] font-bold border', badgeClass, isPulsing && 'animate-pulse')}>
      {label}
    </span>
  )
}

type DecisionModal = {
  rfpId: number
  rfpTitle: string
  decision: 'final_approved' | 'revision_requested' | 'rejected'
} | null

export default function ApprovalsPage() {
  const router = useRouter()
  const [rfps, setRfps] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [isBgRefreshing, setIsBgRefreshing] = useState(false)
  const [modal, setModal] = useState<DecisionModal>(null)
  const [reason, setReason] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [toast, setToast] = useState<{ msg: string; type: 'success' | 'error' } | null>(null)

  const showToast = (msg: string, type: 'success' | 'error' = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3500)
  }

  const loadData = async (bg = false) => {
    if (bg) setIsBgRefreshing(true)
    try {
      const { fetchApi } = await import('@/lib/api')
      const data = await fetchApi('/rfps/submitted-for-review')
      setRfps(data || [])
    } catch (err) {
      console.error('Failed to load approvals', err)
    } finally {
      setLoading(false)
      setIsBgRefreshing(false)
    }
  }

  useEffect(() => {
    loadData()
    const iv = setInterval(() => loadData(true), 15000)
    return () => clearInterval(iv)
  }, [])

  const openDecision = (rfpId: number, rfpTitle: string, decision: DecisionModal['decision']) => {
    setReason('')
    setModal({ rfpId, rfpTitle, decision })
  }

  const confirmDecision = async () => {
    if (!modal || isSubmitting) return
    setIsSubmitting(true)
    try {
      const { fetchApi } = await import('@/lib/api')
      await fetchApi(`/rfps/${modal.rfpId}/final-decision`, {
        method: 'POST',
        body: JSON.stringify({
          decision: modal.decision,
          reason: reason,
          revision_notes: modal.decision === 'revision_requested' ? reason : undefined,
        })
      })
      const labels: Record<string, string> = {
        final_approved: 'Final Approved ✓',
        revision_requested: 'Revision Requested',
        rejected: 'Rejected',
      }
      showToast(`${labels[modal.decision]} — ${modal.rfpTitle}`, modal.decision === 'rejected' ? 'error' : 'success')
      setModal(null)
      loadData(true)
    } catch (e) {
      showToast('Action failed. Please try again.', 'error')
    } finally {
      setIsSubmitting(false)
    }
  }

  const decisionConfig = {
    final_approved:     { label: 'Approve Final',      class: 'bg-emerald-600 hover:bg-emerald-700 text-white', headerClass: 'text-emerald-700', icon: CheckCircle2 },
    revision_requested: { label: 'Request Revision',   class: 'bg-amber-500 hover:bg-amber-600 text-white',   headerClass: 'text-amber-700',   icon: RefreshCw },
    rejected:           { label: 'Reject',             class: 'bg-rose-600 hover:bg-rose-700 text-white',     headerClass: 'text-rose-700',     icon: XCircle },
  }

  return (
    <div className="space-y-6 pb-8 animate-in fade-in duration-500">
      {/* Toast */}
      {toast && (
        <div className={cn(
          'fixed top-6 right-6 z-50 flex items-center gap-3 px-5 py-3 rounded-xl shadow-2xl text-[13px] font-bold text-white animate-in slide-in-from-top-4 duration-300',
          toast.type === 'success' ? 'bg-zinc-900 border border-zinc-800' : 'bg-rose-600'
        )}>
          {toast.type === 'success' ? <CheckCircle2 className="w-4 h-4 text-emerald-400" /> : <AlertCircle className="w-4 h-4" />}
          {toast.msg}
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-xl lg:text-2xl font-bold tracking-tight text-zinc-900">Queue for Approval</h1>
          <p className="text-xs text-zinc-500 mt-1 font-medium">Drafts submitted by Architects requiring your final validation and release decision</p>
        </div>
        <div className="flex items-center gap-6">
          {isBgRefreshing && (
            <span className="flex items-center gap-1.5 text-[10px] font-bold text-zinc-400 uppercase tracking-widest">
              <RefreshCw className="w-2.5 h-2.5 animate-spin" /> Live Sync
            </span>
          )}
          <div className="flex flex-col items-end">
            <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Pending Review</span>
            <span className="text-xl font-black text-amber-600 leading-none mt-1">
              {rfps.filter(r => r.current_status === 'submitted_for_review').length}
            </span>
          </div>
        </div>
      </div>

      {/* Table Container */}
      <div className="premium-card bg-white p-0 overflow-hidden">
        {loading ? (
          <div className="p-8 space-y-4">
            {[1,2,3,4].map(i => <div key={i} className="h-12 bg-zinc-50 rounded-lg animate-pulse" />)}
          </div>
        ) : rfps.length === 0 ? (
          <div className="py-20 flex flex-col items-center text-center">
            <div className="w-14 h-14 rounded-2xl bg-zinc-50 border border-zinc-100 flex items-center justify-center mb-4">
              <FileText className="w-6 h-6 text-zinc-300" />
            </div>
            <h3 className="text-sm font-bold text-zinc-900">No pending approvals</h3>
            <p className="text-xs text-zinc-400 mt-1.5 max-w-xs font-medium leading-relaxed">
              When an architect completes a draft and submits it for review, it will appear here for your approval.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="bg-zinc-50/50 border-b border-zinc-100">
                  {['RFP Details', 'Client', 'Submitted By', 'Deadline', 'Status', 'Decision'].map(h => (
                    <th key={h} className="px-5 py-3 text-left text-[9px] font-black uppercase tracking-widest text-zinc-400">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-50">
                {rfps.map(rfp => {
                  let summary: any = null
                  try { if (rfp.summary_json) summary = JSON.parse(rfp.summary_json) } catch { }
                  const isDecided = rfp.current_status !== 'submitted_for_review'
                  return (
                    <tr key={rfp.id} className="hover:bg-zinc-50/30 transition-colors group">
                      <td className="px-5 py-3">
                        <div className="flex flex-col gap-0.5">
                          <p className="text-[13px] font-bold text-zinc-900 max-w-[220px] truncate group-hover:text-indigo-600 transition-colors">{rfp.title}</p>
                          <p className="text-[9px] font-black text-zinc-400 uppercase tracking-tighter">ID: #{rfp.id}</p>
                        </div>
                      </td>
                      <td className="px-5 py-3 text-[12px] font-medium text-zinc-600">{formatClient(summary?.client_name || rfp.client_name)}</td>
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-2">
                          <div className="w-6 h-6 rounded-full bg-zinc-100 flex items-center justify-center border border-zinc-200">
                            <User className="w-3 h-3 text-zinc-500" />
                          </div>
                          <div className="flex flex-col">
                            <span className="text-[12px] font-bold text-zinc-700">Arch. #{rfp.submitted_by || '—'}</span>
                            {rfp.submitted_at && (
                              <span className="text-[9px] font-medium text-zinc-400">
                                {new Date(rfp.submitted_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-3 text-[12px] font-bold text-zinc-600">
                         {formatDeadline(summary?.deadline)}
                      </td>
                      <td className="px-5 py-3"><StatusBadge status={rfp.current_status} documentQuality={rfp.document_quality} /></td>
                      <td className="px-5 py-3">
                        {isDecided ? (
                          <Badge variant="outline" className="h-5 px-2 text-[9px] font-black uppercase tracking-tighter bg-zinc-100/50 border-none text-zinc-400">Resolved</Badge>
                        ) : (
                          <div className="flex items-center gap-2">
                            <button onClick={() => openDecision(rfp.id, rfp.title, 'final_approved')}
                              className="h-7 px-3 text-[10px] font-black uppercase tracking-widest rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-100 hover:bg-emerald-600 hover:text-white hover:border-emerald-600 transition-all active:scale-95">
                              Approve
                            </button>
                            <button onClick={() => openDecision(rfp.id, rfp.title, 'revision_requested')}
                              className="h-7 px-3 text-[10px] font-black uppercase tracking-widest rounded-lg bg-amber-50 text-amber-700 border border-amber-100 hover:bg-amber-600 hover:text-white hover:border-amber-600 transition-all active:scale-95">
                              Revise
                            </button>
                            <button onClick={() => router.push(`/dashboard/ceo/rfp/${rfp.id}`)}
                              className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-900 hover:bg-zinc-100 transition-all" title="Review Analysis">
                              <ArrowUpRight className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Decision Modal */}
      {modal && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-zinc-900/40 backdrop-blur-sm animate-in fade-in duration-200" onClick={() => setModal(null)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200" onClick={e => e.stopPropagation()}>
            {(() => {
              const cfg = decisionConfig[modal.decision]
              const Icon = cfg.icon
              return (
                <div className="p-6 space-y-5">
                  <div className="flex items-start gap-4">
                    <div className={cn('w-10 h-10 rounded-xl flex items-center justify-center shrink-0 border', 
                      modal.decision === 'final_approved' ? 'bg-emerald-50 border-emerald-100 text-emerald-600' :
                      modal.decision === 'revision_requested' ? 'bg-amber-50 border-amber-100 text-amber-600' : 'bg-rose-50 border-rose-100 text-rose-600'
                    )}>
                      <Icon className="w-5 h-5" />
                    </div>
                    <div className="space-y-1">
                      <h3 className="text-base font-bold text-zinc-900 tracking-tight">{cfg.label}</h3>
                      <p className="text-xs font-medium text-zinc-500 truncate max-w-[280px]">{modal.rfpTitle}</p>
                    </div>
                  </div>
                  
                  <div className="space-y-2">
                    <label className="text-[11px] font-bold text-zinc-400 uppercase tracking-widest block">
                      {modal.decision === 'revision_requested' ? 'Revision Instructions' : 'Internal Notes'}
                    </label>
                    <textarea
                      autoFocus
                      value={reason}
                      onChange={e => setReason(e.target.value)}
                      placeholder={modal.decision === 'revision_requested'
                        ? 'Describe specific changes or sections to refine...'
                        : 'Any final comments for the archive...'}
                      rows={4}
                      className="w-full text-sm font-medium p-4 border border-zinc-200 rounded-xl outline-none focus:ring-4 focus:ring-zinc-900/5 focus:border-zinc-400 transition-all bg-zinc-50 placeholder:text-zinc-400"
                    />
                  </div>

                  <div className="flex gap-3">
                    <button onClick={() => setModal(null)}
                      className="flex-1 h-10 text-[11px] font-bold uppercase tracking-widest border border-zinc-200 rounded-xl text-zinc-500 hover:bg-zinc-50 transition-all active:scale-95">
                      Dismiss
                    </button>
                    <button
                      onClick={confirmDecision}
                      disabled={isSubmitting || (modal.decision === 'revision_requested' && !reason.trim())}
                      className={cn('flex-1 h-10 text-[11px] font-black uppercase tracking-widest rounded-xl transition-all active:scale-95 disabled:opacity-50 shadow-lg shadow-zinc-900/10', cfg.class)}
                    >
                      {isSubmitting ? 'Processing...' : 'Confirm Action'}
                    </button>
                  </div>
                </div>
              )
            })()}
          </div>
        </div>
      )}
    </div>
  )
}
