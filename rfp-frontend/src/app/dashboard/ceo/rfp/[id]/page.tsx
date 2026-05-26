'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import {
  ChevronLeft, Sparkles, AlertTriangle, TrendingUp,
  Send, UserPlus, Ban, Pause, CheckCircle2, Calendar, Clock,
  DollarSign, FileText
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { getStatusInfo, getStatusLabel, formatClient, formatDeadline, formatValue } from '@/lib/statusUtils'

function StatusBadge({ status, documentQuality }: { status: string; documentQuality?: string | null }) {
  const { label, badgeClass } = getStatusInfo(status, documentQuality)
  return <Badge variant="outline" className={cn('text-xs font-semibold', badgeClass)}>{label}</Badge>
}

export default function RfpReviewPage() {
  const params = useParams()
  const router = useRouter()
  const [rfp, setRfp] = useState<any>(null)
  const [aiSummary, setAiSummary] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  const [architects, setArchitects] = useState<any[]>([])
  const [isAssignModalOpen, setIsAssignModalOpen] = useState(false)
  const [selectedArchitect, setSelectedArchitect] = useState('')
  const [lengthMode, setLengthMode] = useState('short')
  const [isAssigning, setIsAssigning] = useState(false)
  const [hasConfirmedTiny, setHasConfirmedTiny] = useState(false)


  const [isDecisionModalOpen, setIsDecisionModalOpen] = useState(false)
  const [pendingDecision, setPendingDecision] = useState<'approved' | 'rejected' | 'on_hold' | null>(null)
  const [decisionReason, setDecisionReason] = useState('')
  const [isSubmittingDecision, setIsSubmittingDecision] = useState(false)

  const [chatInput, setChatInput] = useState('')
  const [knowledgeMode, setKnowledgeMode] = useState('Hybrid')
  const [isChatLoading, setIsChatLoading] = useState(false)
  const [messages, setMessages] = useState<{ role: 'ai' | 'user'; text: string }[]>([
    { role: 'ai', text: 'Hello! I am your AI Advisor. Ask me anything about this RFP — key requirements, risks, compliance, or strategy.' }
  ])

  useEffect(() => {
    async function loadData() {
      try {
        const { fetchApi } = await import('@/lib/api')
        const rfpData = await fetchApi(`/rfps/${params.id}`)
        let sumData: any = null
        try {
          sumData = await fetchApi(`/rfps/${params.id}/summary`)
          if (!sumData?.error) setAiSummary(sumData)
        } catch { }

        // Parse summary_json from rfpData if sumData not available
        if (!sumData && rfpData.summary_json) {
          try {
            const parsed = JSON.parse(rfpData.summary_json)
            setAiSummary({ summary: parsed, ...parsed })
          } catch { }
        }

        setRfp(rfpData)
        try {
          const archData = await fetchApi('/auth/users/architects')
          setArchitects(archData || [])
        } catch { }
      } catch (e) {
        console.error('Failed to load RFP', e)
      } finally {
        setLoading(false)
      }
    }
    if (params.id) loadData()
  }, [params.id])

  const isDecided = rfp?.current_status === 'approved' || rfp?.current_status === 'rejected'
    || rfp?.current_status === 'on_hold' || rfp?.current_status === 'assigned_to_sa'

  const handleDecision = async () => {
    if (!pendingDecision || isSubmittingDecision) return
    setIsSubmittingDecision(true)
    try {
      const { fetchApi } = await import('@/lib/api')
      await fetchApi(`/rfps/${params.id}/decision`, {
        method: 'POST',
        body: JSON.stringify({ decision: pendingDecision, reason: decisionReason })
      })
      setRfp((prev: any) => ({ ...prev, current_status: pendingDecision }))
      setIsDecisionModalOpen(false)
      setPendingDecision(null)
      setDecisionReason('')
      // Immediately refresh notification bell after PM decision
      window.__refetchNotifications?.()
    } catch (e) { console.error(e) }
    finally { setIsSubmittingDecision(false) }
  }

  const handleAssignArchitect = async () => {
    if (!selectedArchitect || isAssigning) return
    setIsAssigning(true)
    try {
      const { fetchApi } = await import('@/lib/api')
      await fetchApi(`/rfps/${params.id}/assign-architect`, {
        method: 'POST',
        body: JSON.stringify({
          architect_id: parseInt(selectedArchitect),
          notes: '',
          length_mode: lengthMode
        })
      })
      setIsAssignModalOpen(false)
      setRfp((prev: any) => ({ ...prev, current_status: 'assigned_to_sa' }))
      // Immediately refresh notification bell after SA assignment
      window.__refetchNotifications?.()
    } catch (e) { console.error(e) }
    finally { setIsAssigning(false) }
  }

  const handleSendMessage = async (e?: React.FormEvent, preset?: string) => {
    e?.preventDefault()
    const msg = preset || chatInput
    if (!msg.trim() || isChatLoading) return
    setMessages(prev => [...prev, { role: 'user', text: msg }])
    setChatInput('')
    setIsChatLoading(true)
    try {
      const { API_BASE_URL } = await import('@/lib/api')
      const token = localStorage.getItem('rfp_token')
      const res = await fetch(`${API_BASE_URL}/rfps/${params.id}/chat-stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ message: msg, knowledge_mode: knowledgeMode, history: messages.slice(-6) })
      })
      if (!res.ok) throw new Error('Failed')
      const reader = res.body?.getReader()
      if (!reader) throw new Error('No reader')
      setMessages(prev => [...prev, { role: 'ai', text: '' }])
      let acc = ''
      const decoder = new TextDecoder()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        
        // Handle SSE or raw text
        if (chunk.includes('event: message')) {
          try {
            const dataLine = chunk.split('\n').find(l => l.startsWith('data: '))
            if (dataLine) {
              const data = JSON.parse(dataLine.replace('data: ', ''))
              if (data.content) {
                acc += data.content
                setMessages(prev => { const n = [...prev]; n[n.length - 1] = { role: 'ai', text: acc }; return n })
              }
            }
          } catch (e) { acc += chunk; }
        } else if (!chunk.includes('event: done')) {
          acc += chunk
          setMessages(prev => { const n = [...prev]; n[n.length - 1] = { role: 'ai', text: acc }; return n })
        }
      }
    } catch {
      setMessages(prev => [...prev, { role: 'ai', text: 'AI Advisor unavailable. Please try again.' }])
    } finally { setIsChatLoading(false) }
  }

  // Extract summary data safely
  const summary = aiSummary?.summary || aiSummary || {}
  const risks = summary?.risks || []
  const winProb = summary?.win_probability || aiSummary?.win_probability || null
  const execSummary = summary?.executive_summary || aiSummary?.executive_summary || ''
 
  const getPmActionState = () => {
    const status = rfp?.current_status || 'uploaded'
    const isInsufficient = rfp?.document_quality === 'insufficient_rfp_detail' || status === 'needs_more_detail'
    const isExtractionIssue = rfp?.document_quality === 'extraction_failed_or_scanned_pdf' || status === 'extraction_needs_review'
    const isAssigned = !!rfp?.assigned_to_id || status === 'assigned_to_sa' || status.includes('draft_') || status === 'ai_draft_ready' || status === 'draft_complete'
    
    return {
      isInsufficient,
      isExtractionIssue,
      showInitialDecision: !isInsufficient && !isExtractionIssue && ["uploaded", "ready_for_pm_review", "pending-review", "pending_review", "analysis_complete", "summary_generated", "under_review", "awaiting_ceo_decision"].includes(status),
      showAssignArchitect: status === "approved" && !isAssigned,
      showAssignedInfo: isAssigned && !["ready_for_pm_review", "pending-review"].includes(status),
      showGoToApprovals: ["submitted_for_review", "final_approved", "revision_requested"].includes(status),
      isFinalApproved: status === "final_approved",
      isRejected: status === "rejected",
      statusLabel: getStatusLabel(status)
    }
  }
 
  const pmState = getPmActionState()

  if (loading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-8 w-64 bg-zinc-100 rounded" />
        <div className="grid grid-cols-3 gap-4">
          {[1,2,3].map(i => <div key={i} className="h-24 bg-zinc-100 rounded-xl" />)}
        </div>
        <div className="h-48 bg-zinc-100 rounded-xl" />
      </div>
    )
  }

  if (!rfp) return (
    <div className="flex items-center justify-center h-48 text-zinc-400 text-sm">RFP not found.</div>
  )

  return (
    <div className="space-y-6 pb-8 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div className="space-y-2">
          <button onClick={() => router.back()} className="group flex items-center gap-1.5 text-[10px] font-bold text-zinc-400 hover:text-zinc-900 transition-colors uppercase tracking-widest">
            <ChevronLeft className="w-3 h-3 group-hover:-translate-x-0.5 transition-transform" /> Back
          </button>
          <div className="space-y-1">
            <h1 className="text-xl lg:text-2xl font-bold text-zinc-900 tracking-tight leading-tight">{rfp.title}</h1>
            <div className="flex items-center gap-2.5">
              <StatusBadge status={rfp.current_status} documentQuality={rfp.document_quality} />
              <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">ID #{rfp.id}</span>
            </div>
          </div>
        </div>

        {/* Extraction Failure Warning */}
        {pmState.isExtractionIssue && (
          <div className="w-full md:max-w-xl p-4 bg-amber-50 border border-amber-200 rounded-2xl flex items-start gap-4 shadow-sm animate-in slide-in-from-top-4 duration-500">
            <div className="w-10 h-10 rounded-xl bg-amber-100 flex items-center justify-center shrink-0">
              <AlertTriangle className="w-5 h-5 text-amber-600" />
            </div>
            <div className="space-y-1">
              <p className="text-[13px] font-bold text-amber-900 uppercase tracking-tight">Extraction Needs Review</p>
              <p className="text-xs text-amber-700 font-medium leading-relaxed">
                Text extraction returned very little content. This PDF may be scanned or image-based. 
                Please upload a text-based PDF/DOCX or enable OCR.
              </p>
            </div>
          </div>
        )}

        {/* Richness Warning Banner */}
        {pmState.isInsufficient && (
          <div className="w-full md:max-w-xl p-4 bg-amber-50 border border-amber-200 rounded-2xl flex items-start gap-4 shadow-sm animate-in slide-in-from-top-4 duration-500">
            <div className="w-10 h-10 rounded-xl bg-amber-100 flex items-center justify-center shrink-0">
              <AlertTriangle className="w-5 h-5 text-amber-600" />
            </div>
            <div className="space-y-1">
              <p className="text-[13px] font-bold text-amber-900 uppercase tracking-tight">Insufficient RFP Detail</p>
              <p className="text-xs text-amber-700 font-medium leading-relaxed">
                This document does not contain enough RFP detail for full proposal generation.
                AI analysis has been skipped to save resources.
              </p>
              <div className="flex items-center gap-3 mt-2">
                <Button size="sm" variant="outline" className="h-7 text-[10px] font-bold bg-white text-amber-800 border-amber-200 hover:bg-amber-100"
                  onClick={() => setIsAssignModalOpen(true)}
                >
                  Generate Brief Response
                </Button>
                <Button size="sm" variant="ghost" className="h-7 text-[10px] font-bold text-zinc-500 hover:text-rose-600"
                   onClick={() => { setPendingDecision('rejected'); setIsDecisionModalOpen(true) }}
                >
                  Ignore/Delete
                </Button>
              </div>
            </div>
          </div>
        )}

        <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap">

          {pmState.isFinalApproved && (
            <div className="h-9 px-4 rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-100 text-[11px] font-bold flex items-center gap-2 uppercase tracking-wider">
              <CheckCircle2 className="w-3.5 h-3.5" /> Approved Final
            </div>
          )}
          {pmState.isRejected && (
            <div className="h-9 px-4 rounded-lg bg-rose-50 text-rose-700 border border-rose-100 text-[11px] font-bold flex items-center gap-2 uppercase tracking-wider">
              <Ban className="w-3.5 h-3.5" /> Rejected
            </div>
          )}
          
          {pmState.showInitialDecision && (
            <div className="flex items-center gap-2 bg-zinc-100/50 p-1 rounded-xl border border-zinc-200/50">
              <Button variant="ghost" size="sm" onClick={() => { setPendingDecision('on_hold'); setIsDecisionModalOpen(true) }}
                className="h-8 text-[11px] font-bold gap-1.5 text-zinc-500 hover:text-zinc-900 rounded-lg">
                <Pause className="w-3.5 h-3.5" /> Hold
              </Button>
              <Button variant="ghost" size="sm" onClick={() => { setPendingDecision('rejected'); setIsDecisionModalOpen(true) }}
                className="h-8 text-[11px] font-bold gap-1.5 text-rose-500 hover:text-rose-600 hover:bg-rose-50 rounded-lg">
                <Ban className="w-3.5 h-3.5" /> Reject
              </Button>
              <Button size="sm" onClick={() => { setPendingDecision('approved'); setIsDecisionModalOpen(true) }}
                className="h-8 text-[11px] font-bold gap-1.5 bg-zinc-900 text-white hover:bg-zinc-800 rounded-lg shadow-sm">
                <CheckCircle2 className="w-3.5 h-3.5" /> Approve
              </Button>
            </div>
          )}

          {pmState.showAssignArchitect && (
            <Button size="sm"
              onClick={() => setIsAssignModalOpen(true)}
              className="h-9 text-[11px] font-bold gap-2 bg-indigo-600 hover:bg-indigo-700 text-white px-5 rounded-lg shadow-md shadow-indigo-100 transition-all active:scale-95">
              <UserPlus className="w-3.5 h-3.5" />
              Assign Architect
            </Button>
          )}

          {pmState.showAssignedInfo && (
            <div className="flex items-center gap-2">
               <Badge className="h-9 px-4 rounded-lg bg-indigo-50/50 text-indigo-700 border-indigo-200/60 text-[11px] font-bold uppercase tracking-wider">
                Assigned to Architect
              </Badge>
              {pmState.showGoToApprovals && (
                <Button size="sm" onClick={() => router.push('/dashboard/ceo/approvals')}
                  className="h-9 text-[11px] font-bold gap-2 bg-zinc-900 text-white rounded-lg px-4 transition-all active:scale-95">
                  View Approval
                </Button>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left 8/12: Metrics & Content */}
        <div className="lg:col-span-8 space-y-6">
          {/* Quick metrics row */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              { icon: FileText, label: 'Client', value: formatClient(summary?.client_name || rfp.client_name) },
              { icon: Calendar, label: 'Deadline', value: formatDeadline(summary?.deadline) },
              { icon: DollarSign, label: 'Value', value: formatValue(summary?.value || summary?.contract_value) },
              { icon: Clock, label: 'Duration', value: summary?.contract_duration || 'TBD' },
            ].map((m, i) => (
              <div key={i} className="premium-card p-3.5 flex flex-col justify-between">
                <div className="flex items-center gap-2 mb-2">
                  <div className="p-1 rounded bg-zinc-50 border border-zinc-100">
                    <m.icon className="w-3 h-3 text-zinc-400" />
                  </div>
                  <span className="text-[9px] font-bold uppercase tracking-widest text-zinc-400">{m.label}</span>
                </div>
                <p className="text-[13px] font-bold text-zinc-900 truncate">{m.value}</p>
              </div>
            ))}
          </div>

          {/* Executive Summary */}
          <Card className="premium-card border-none shadow-none bg-white">
            <CardHeader className="pb-3 pt-5 px-5">
              <CardTitle className="text-[13px] font-bold text-zinc-900 flex items-center gap-2 uppercase tracking-widest">
                <Sparkles className="w-4 h-4 text-indigo-500" /> Executive Analysis
              </CardTitle>
            </CardHeader>
            <CardContent className="px-5 pb-6">
              {execSummary ? (
                <p className="text-[14px] text-zinc-600 leading-relaxed font-medium">{execSummary}</p>
              ) : (
                <p className="text-sm text-zinc-400 italic">
                  {rfp.current_status === 'uploaded' ? 'Click "Analyze" to generate the AI summary.' : 'Summary not yet generated.'}
                </p>
              )}
            </CardContent>
          </Card>

          {/* Risks + Recommendation */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <Card className="premium-card border-none bg-rose-50/20">
              <CardHeader className="pb-3 pt-5 px-5">
                <CardTitle className="text-[11px] font-bold text-rose-800 flex items-center gap-2 uppercase tracking-widest">
                  <AlertTriangle className="w-3.5 h-3.5" /> Risk Signals
                </CardTitle>
              </CardHeader>
              <CardContent className="px-5 pb-5">
                {risks.length > 0 ? (
                  <ul className="space-y-3">
                    {risks.slice(0, 5).map((r: any, i: number) => (
                      <li key={i} className="flex items-start gap-3">
                        <div className={cn('mt-1.5 w-1.5 h-1.5 rounded-full shrink-0', {
                          'bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.4)]': r.severity === 'high',
                          'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.4)]': r.severity === 'medium',
                          'bg-emerald-500': r.severity === 'low',
                        })} />
                        <div className="flex flex-col gap-0.5">
                          <span className="text-[13px] font-bold text-zinc-900 leading-tight">{r.risk}</span>
                          <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-tight">{r.severity} severity</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-zinc-400 italic">No risks identified yet.</p>
                )}
              </CardContent>
            </Card>

            <Card className="premium-card border-none bg-indigo-50/20">
              <CardHeader className="pb-3 pt-5 px-5">
                <CardTitle className="text-[11px] font-bold text-indigo-800 flex items-center gap-2 uppercase tracking-widest">
                  <TrendingUp className="w-3.5 h-3.5" /> Advisor Suggestion
                </CardTitle>
              </CardHeader>
              <CardContent className="px-5 pb-5 flex flex-col justify-between h-full">
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">Recommendation</span>
                    <Badge className="bg-indigo-600 text-white text-[10px] font-black uppercase tracking-wider h-5 px-1.5 rounded">
                      {summary?.recommended_action || 'Pending'}
                    </Badge>
                  </div>
                  <p className="text-[13px] text-zinc-600 leading-relaxed font-medium">
                    {summary?.next_steps || summary?.recommendation_reason || 'Analyze the proposal complexity and team availability before assigning a Solution Architect.'}
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Win Probability & Requirements side by side */}
          <div className="grid grid-cols-1 md:grid-cols-5 gap-6">
            {winProb && (
              <div className="md:col-span-2 premium-card p-5 bg-white">
                <div className="flex items-center justify-between mb-5">
                  <span className="text-[11px] font-bold text-zinc-400 uppercase tracking-widest">Win Probability</span>
                  <span className="text-3xl font-black text-zinc-900 tracking-tighter">{winProb}%</span>
                </div>
                <div className="space-y-5">
                  {[
                    { label: 'Technical Alignment', value: 85 },
                    { label: 'Strategic Value', value: 65 },
                    { label: 'Complexity', value: 45 },
                  ].map((s, i) => (
                    <div key={i} className="space-y-2">
                      <div className="flex justify-between text-[10px] font-bold text-zinc-500 uppercase tracking-wider">
                        <span>{s.label}</span><span className="text-zinc-900 font-black">{s.value}%</span>
                      </div>
                      <div className="w-full bg-zinc-100 h-1 rounded-full overflow-hidden">
                        <div className="h-full bg-zinc-900 rounded-full transition-all duration-1000" style={{ width: `${s.value}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className={cn("premium-card p-5 bg-white", winProb ? "md:col-span-3" : "md:col-span-5")}>
              <h3 className="text-[11px] font-bold text-zinc-400 uppercase tracking-widest mb-4">Key Functional Requirements</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3">
                {(summary?.key_requirements || summary?.functional_requirements || []).slice(0, 8).map((r: string, i: number) => (
                  <div key={i} className="flex items-start gap-3 group">
                    <div className="mt-1.5 w-1 h-1 rounded-full bg-indigo-500 group-hover:scale-150 transition-transform shrink-0" />
                    <span className="text-[12px] font-medium text-zinc-600 leading-snug line-clamp-2">{r}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Right 4/12: AI Advisor */}
        <div className="lg:col-span-4">
          <Card className="premium-card border-none bg-white sticky top-20 shadow-xl shadow-zinc-200/50">
            <CardHeader className="p-4 border-b border-zinc-100 bg-zinc-50/30">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-zinc-900 flex items-center justify-center shadow-lg shadow-zinc-900/20">
                    <Sparkles className="w-4 h-4 text-white" />
                  </div>
                  <div>
                    <CardTitle className="text-[13px] font-black text-zinc-900 tracking-tight">AI Advisor</CardTitle>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                      <span className="text-[9px] font-black text-emerald-600 uppercase tracking-widest">Active Insight</span>
                    </div>
                  </div>
                </div>
                <Select value={knowledgeMode} onValueChange={setKnowledgeMode}>
                  <SelectTrigger className="h-7 w-24 text-[10px] font-bold uppercase tracking-widest bg-white border-zinc-200 rounded-lg outline-none">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="rounded-xl border-zinc-200">
                    <SelectItem value="Hybrid" className="text-[10px] font-bold uppercase">Hybrid</SelectItem>
                    <SelectItem value="RFP-Only" className="text-[10px] font-bold uppercase">RFP Only</SelectItem>
                    <SelectItem value="Global" className="text-[10px] font-bold uppercase">Global</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <div className="h-[400px] overflow-y-auto p-4 space-y-4 bg-zinc-50/20 scroll-smooth">
                {messages.map((msg, i) => (
                  <div key={i} className={cn('flex flex-col animate-in fade-in slide-in-from-bottom-1 duration-300', msg.role === 'ai' ? 'items-start' : 'items-end')}>
                    <div className={cn(
                      'max-w-[90%] px-4 py-2.5 text-[13px] leading-relaxed rounded-2xl shadow-sm',
                      msg.role === 'ai'
                        ? 'bg-white border border-zinc-100 text-zinc-700 rounded-tl-none font-medium'
                        : 'bg-zinc-900 text-white rounded-tr-none font-bold'
                    )}>
                      {msg.role === 'ai'
                        ? <div className="prose prose-sm prose-zinc max-w-none"><ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown></div>
                        : msg.text}
                    </div>
                  </div>
                ))}
                {isChatLoading && (
                  <div className="flex justify-start">
                    <div className="bg-white border border-zinc-100 rounded-2xl rounded-tl-none px-4 py-3 flex gap-1.5 items-center shadow-sm">
                      <div className="w-1.5 h-1.5 rounded-full bg-zinc-300 animate-bounce" />
                      <div className="w-1.5 h-1.5 rounded-full bg-zinc-300 animate-bounce [animation-delay:0.2s]" />
                      <div className="w-1.5 h-1.5 rounded-full bg-zinc-300 animate-bounce [animation-delay:0.4s]" />
                    </div>
                  </div>
                )}
              </div>

              <div className="p-4 bg-white border-t border-zinc-100 space-y-3">
                <div className="flex flex-wrap gap-1.5">
                  {['Key summary', 'Compliance', 'Risk matrix'].map((p, i) => (
                    <button key={i} onClick={() => handleSendMessage(undefined, p)}
                      className="px-2.5 py-1.5 text-[10px] font-bold text-zinc-500 bg-zinc-50 border border-zinc-100 rounded-lg hover:border-zinc-900 hover:text-zinc-900 hover:bg-white transition-all uppercase tracking-tight">
                      {p}
                    </button>
                  ))}
                </div>

                <div className="relative group">
                  <textarea
                    value={chatInput}
                    onChange={e => setChatInput(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSendMessage() } }}
                    placeholder="Ask Advisor..."
                    className="w-full min-h-[90px] p-3.5 text-xs font-bold border border-zinc-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-zinc-900/5 focus:border-zinc-900 transition-all resize-none bg-zinc-50/50 placeholder:text-zinc-400 placeholder:font-medium"
                  />
                  <Button onClick={handleSendMessage} disabled={!chatInput.trim() || isChatLoading}
                    className="absolute bottom-2.5 right-2.5 h-8 w-8 p-0 bg-zinc-900 hover:bg-zinc-800 text-white rounded-lg transition-all active:scale-90 disabled:opacity-30 shadow-lg shadow-zinc-900/20">
                    <Send className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Assign Architect Dialog */}
      <Dialog open={isAssignModalOpen} onOpenChange={setIsAssignModalOpen}>
        <DialogContent className="sm:max-w-[400px] rounded-2xl">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold">Assign Solution Architect</DialogTitle>
          </DialogHeader>
          <div className="py-4 space-y-4">
            <p className="text-sm text-zinc-500">Select an architect to lead the technical response for this RFP.</p>
            
            {/* Richness Warning */}
            {(() => {
              try {
                const summary = rfp?.summary_json ? JSON.parse(rfp.summary_json) : null;
                if (summary?.document_quality === 'insufficient_rfp_detail') {
                  return (
                    <div className="p-3 bg-amber-50 border border-amber-100 rounded-xl space-y-2">
                      <div className="flex items-center gap-2 text-amber-700">
                        <AlertTriangle className="w-4 h-4" />
                        <span className="text-[11px] font-bold uppercase tracking-tight">Limited RFP Detail Detected</span>
                      </div>
                      <p className="text-[10px] text-amber-600 leading-relaxed font-medium">
                        This document appears to have limited content ({summary.word_count || 'few'} words). 
                        Generating a full proposal may produce generic assumptions. 
                        <strong> System will use "Brief Response" mode (2-5 pages).</strong>
                      </p>
                      <div className="flex items-center gap-2 pt-1">
                        <input 
                          type="checkbox" 
                          id="confirm-tiny" 
                          className="w-3 h-3 rounded border-amber-300 text-amber-600 focus:ring-amber-500" 
                          onChange={(e) => setHasConfirmedTiny(e.target.checked)}
                        />
                        <label htmlFor="confirm-tiny" className="text-[10px] font-bold text-amber-700 cursor-pointer">
                          I understand and want to continue
                        </label>
                      </div>
                    </div>
                  );
                }
              } catch (e) {}
              return null;
            })()}

            <Select onValueChange={setSelectedArchitect} value={selectedArchitect}>
              <SelectTrigger className="h-10 rounded-xl border-zinc-200 text-sm">
                <SelectValue placeholder="Select an architect" />
              </SelectTrigger>
              <SelectContent className="rounded-xl border-zinc-200">
                {architects.map(a => (
                  <SelectItem key={a.id} value={a.id.toString()} className="py-2.5 text-sm">
                    <div className="flex flex-col">
                      <span className="font-semibold text-zinc-900">{a.name}</span>
                      <span className="text-[10px] text-zinc-400 uppercase tracking-wide">Solution Architect</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <div className="pt-2">
              <label className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider mb-1.5 block">Proposal Length Mode</label>
              <Select onValueChange={setLengthMode} value={lengthMode}>
                <SelectTrigger className="h-10 rounded-xl border-zinc-200 text-sm">
                  <SelectValue placeholder="Select mode" />
                </SelectTrigger>
                <SelectContent className="rounded-xl border-zinc-200">
                  <SelectItem value="short" className="py-2.5">
                    <div className="flex flex-col">
                      <span className="font-semibold text-zinc-900">Short Draft</span>
                      <span className="text-[10px] text-zinc-400">Target: 25–40 pages (Compact)</span>
                    </div>
                  </SelectItem>
                  <SelectItem value="standard" className="py-2.5">
                    <div className="flex flex-col">
                      <span className="font-semibold text-zinc-900">Standard Draft</span>
                      <span className="text-[10px] text-zinc-400">Target: 60–80 pages (Balanced)</span>
                    </div>
                  </SelectItem>
                  <SelectItem value="full" className="py-2.5">
                    <div className="flex flex-col">
                      <span className="font-semibold text-zinc-900">Full Proposal</span>
                      <span className="text-[10px] text-zinc-400">Target: 90–120 pages (Comprehensive)</span>
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="ghost" size="sm" onClick={() => setIsAssignModalOpen(false)}>Cancel</Button>
            <Button size="sm" onClick={handleAssignArchitect} 
              disabled={!selectedArchitect || isAssigning || (rfp?.summary_json?.includes('insufficient_rfp_detail') && !hasConfirmedTiny)}
              className="bg-blue-600 hover:bg-blue-700 text-white rounded-xl px-6 text-xs font-bold">
              {isAssigning ? 'Assigning...' : 'Confirm'}
            </Button>
          </DialogFooter>

        </DialogContent>
      </Dialog>

      {/* Decision Dialog */}
      <Dialog open={isDecisionModalOpen} onOpenChange={setIsDecisionModalOpen}>
        <DialogContent className="sm:max-w-[400px] rounded-2xl">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold">
              {pendingDecision === 'approved' ? 'Approve RFP' : pendingDecision === 'rejected' ? 'Reject RFP' : 'Put on Hold'}
            </DialogTitle>
          </DialogHeader>
          <div className="py-4 space-y-3">
            <p className="text-sm text-zinc-500">Please provide a brief reason for your decision.</p>
            <textarea value={decisionReason} onChange={e => setDecisionReason(e.target.value)}
              placeholder="Enter reason..." rows={3}
              className="w-full p-3 text-sm border border-zinc-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-zinc-900/10 resize-none bg-zinc-50" />
          </div>
          <DialogFooter className="gap-2">
            <Button variant="ghost" size="sm" onClick={() => setIsDecisionModalOpen(false)}>Cancel</Button>
            <Button size="sm" onClick={handleDecision} disabled={isSubmittingDecision}
              className={cn('rounded-xl px-6 text-xs font-bold text-white', {
                'bg-emerald-600 hover:bg-emerald-700': pendingDecision === 'approved',
                'bg-rose-600 hover:bg-rose-700': pendingDecision === 'rejected',
                'bg-zinc-900 hover:bg-zinc-800': pendingDecision === 'on_hold',
              })}>
              {isSubmittingDecision ? 'Submitting...' : 'Confirm'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
