'use client'

import { useState, useEffect } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { Suspense } from 'react'
import { Save, Send, RefreshCw, Download, Sparkles, FileText, ChevronLeft, CheckCircle2, Clock, AlertCircle, AlertTriangle, TableProperties } from 'lucide-react'

import { cn } from '@/lib/utils'
import { getStatusInfo } from '@/lib/statusUtils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useRFPStore } from '@/store/rfpStore'
import { 
  Select, 
  SelectContent, 
  SelectItem, 
  SelectTrigger, 
  SelectValue 
} from '@/components/ui/select'

// ─── Proposal TOC Structure ────────────────────────────────────────────────
// ─── Proposal TOC Structure (Dynamic based on mode) ───────────────────────
const SECTIONS_SHORT = [
  { order: 1,  name: 'Executive Summary' },
  { order: 2,  name: 'Understanding of RFP' },
  { order: 3,  name: 'Proposed Solution Overview' },
  { order: 4,  name: 'Functional Coverage' },
  { order: 5,  name: 'Technical Architecture' },
  { order: 6,  name: 'Integration Approach' },
  { order: 7,  name: 'Data Migration Approach' },
  { order: 8,  name: 'Implementation Plan' },
  { order: 9,  name: 'Testing and Quality' },
  { order: 10, name: 'Security and Compliance' },
  { order: 11, name: 'SLA / O&M' },
  { order: 12, name: 'Risk and Mitigation' },
  { order: 13, name: 'Compliance Summary' },
  { order: 14, name: 'Conclusion' },
]

const SECTIONS_STANDARD = [
  { order: 1,  name: "Executive Summary" },
  { order: 2,  name: "Understanding of RFP Requirements" },
  { order: 3,  name: "Proposed Solution Overview" },
  { order: 4,  name: "System Architecture" },
  { order: 5,  name: "Functional Solution Architecture" },
  { order: 6,  name: "User Roles and Workflow Coverage" },
  { order: 7,  name: "Integration Architecture" },
  { order: 8,  name: "Data Migration Strategy" },
  { order: 9,  name: "Implementation Strategy and Timeline" },
  { order: 10, name: "Project Governance and Resource Deployment" },
  { order: 11, name: "Testing and Quality Assurance Strategy" },
  { order: 12, name: "Training and Change Management" },
  { order: 13, name: "Operations and Maintenance Strategy" },
  { order: 14, name: "Service Level Agreements and KPIs" },
  { order: 15, name: "Security and Compliance Framework" },
  { order: 16, name: "Risk Management and Mitigation Strategy" },
  { order: 17, name: "Conclusion" },
  { order: 18, name: "Annexure 1 - Compliance Matrix" },
  { order: 19, name: "Annexure 2 - Technical Architecture" },
  { order: 20, name: "Annexure 3 - Implementation Plan and Team" },
]

const SECTIONS_FULL = [
  ...SECTIONS_STANDARD,
  { order: 21, name: "Annexure 4 - Case Studies" },
  { order: 22, name: "Annexure 5 - Resumes of Key Personnel" },
]

const getSectionsForMode = (mode?: string) => {
  if (mode === 'short') return SECTIONS_SHORT
  if (mode === 'full') return SECTIONS_FULL
  return SECTIONS_STANDARD
}

function TOCPanel({ generatedSections, totalSections, mode }: { generatedSections: Set<string>; totalSections: number; mode?: string }) {
  const sections = getSectionsForMode(mode)
  return (
    <div className="bg-white border border-zinc-200 rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-zinc-100 bg-zinc-50">
        <h3 className="text-xs font-bold text-zinc-900 uppercase tracking-wider">Proposal Structure ({mode?.toUpperCase() || 'STANDARD'})</h3>
        <p className="text-[10px] text-zinc-500 mt-0.5">{generatedSections.size}/{sections.length} sections generated</p>
      </div>
      <div className="p-2 max-h-72 overflow-y-auto space-y-0.5">
        {sections.map(sec => {
          const isGenerated = generatedSections.has(sec.name)
          const isAnnexure = sec.name.startsWith('Annexure')
          return (
            <div key={sec.order} className={cn(
              'flex items-center gap-2 px-2 py-1.5 rounded-lg transition-colors text-xs',
              isGenerated ? 'text-zinc-700' : 'text-zinc-400',
              isAnnexure ? 'border-t border-zinc-100 mt-1 pt-2' : ''
            )}>
              <div className={cn('w-4 h-4 rounded-full flex items-center justify-center shrink-0 text-[8px] font-black', {
                'bg-emerald-100 text-emerald-600': isGenerated,
                'bg-zinc-100 text-zinc-400': !isGenerated,
              })}>
                {isGenerated ? '✓' : sec.order}
              </div>
              <span className={cn('truncate', isGenerated ? 'font-medium' : 'font-normal')}>
                {sec.order}. {sec.name}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
function WorkspaceContent() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const rfpId = searchParams.get('id') || '1'
  
  const { saRfps } = useRFPStore()
  const cachedRfp = saRfps.find((r: any) => String(r.id) === String(rfpId))

  const [rfp, setRfp] = useState<any>(cachedRfp || null)
  const [drafts, setDrafts] = useState<any[]>([])
  const [loading, setLoading] = useState(!cachedRfp)
  const [isRegenerating, setIsRegenerating] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [progress, setProgress] = useState<{ current: number; total: number; statusMsg?: string; lastActivity?: string; generation_mode?: string; generated_document?: any; compliance_matrix?: any; status?: string; is_complete?: boolean } | null>(null)
  const [generatedSections, setGeneratedSections] = useState<Set<string>>(new Set())
  const [quality, setQuality] = useState<any>(null)
  const [toast, setToast] = useState<{msg: string; type: 'success'|'error'} | null>(null)

  const [chatInput, setChatInput] = useState('')
  const [knowledgeMode, setKnowledgeMode] = useState('Hybrid')
  const [isChatLoading, setIsChatLoading] = useState(false)
  const [messages, setMessages] = useState<{ role: 'ai' | 'user'; text: string }[]>([
    { role: 'ai', text: 'Hello! I am your AI Architect Assistant. Ask me anything about this RFP or proposal sections.' }
  ])

  const showToast = (msg: string, type: 'success' | 'error' = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3500)
  }

  const loadData = async () => {
    try {
      const { fetchApi } = await import('@/lib/api')
      const rfpData = await fetchApi(`/rfps/${rfpId}`)
      setRfp(rfpData)

      // Load drafts (sections)
      try {
        const prog = await fetchApi(`/rfps/${rfpId}/generation-progress`)
        setProgress({ 
          current: prog.current, 
          total: prog.total, 
          statusMsg: prog.status_message,
          lastActivity: prog.last_activity,
          generation_mode: prog.generation_mode,
          generated_document: prog.generated_document,
          compliance_matrix: prog.compliance_matrix,
          status: prog.status,
          is_complete: prog.is_complete
        })
        const sectionNames = new Set<string>()
        if (prog.current > 0) {
          const sections = getSectionsForMode(prog.generation_mode)
          sections.slice(0, prog.current).forEach(s => sectionNames.add(s.name))
        }
        setGeneratedSections(sectionNames)
      } catch { }

      // Load quality status
      try {
        const q = await fetchApi(`/rfps/${rfpId}/quality-status`)
        setQuality(q)
      } catch { }
    } catch (e) {
      console.error('Workspace load error:', e)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmitForReview = async () => {
    if (isSubmitting) return
    setIsSubmitting(true)
    try {
      const { fetchApi } = await import('@/lib/api')
      await fetchApi(`/rfps/${rfpId}/submit-review`, {
        method: 'POST',
        body: JSON.stringify({ notes: '' })
      })
      showToast('Draft submitted for PM review ✓', 'success')
      setRfp((prev: any) => ({ ...prev, current_status: 'submitted_for_review' }))
      // Refresh notification bell immediately after SA submits for PM review
      window.__refetchNotifications?.()
    } catch {
      showToast('Submission failed. Please try again.', 'error')
    } finally {
      setIsSubmitting(false)
    }
  }


  useEffect(() => {
    loadData()
    
    // Passive poll if generation is in progress
    let interval: any;
    if (rfp?.current_status === 'generating_draft' || rfp?.current_status === 'in_drafting' || rfp?.current_status === 'generation_running' || rfp?.current_status === 'generation_queued') {
      interval = setInterval(async () => {
        try {
          const { fetchApi } = await import('@/lib/api')
          const prog = await fetchApi(`/rfps/${rfpId}/generation-progress`)
          setProgress(prog)
          if (prog.status === 'completed' || prog.is_complete || prog.status === 'failed') {
            clearInterval(interval)
            loadData()
            window.__refetchNotifications?.()
          }
        } catch { clearInterval(interval) }
      }, 8000)
    }
    
    return () => { if (interval) clearInterval(interval) }
  }, [rfpId, rfp?.current_status])


  const handleRegenerate = async () => {
    if (isRegenerating) return
    if (!confirm("This may overwrite or restart the current draft. Continue?")) return
    
    setIsRegenerating(true)
    setProgress({ current: 0, total: 14 }) // Default to short total, will update on first poll
    try {
      const { fetchApi } = await import('@/lib/api')
      await fetchApi(`/rfps/${rfpId}/regenerate`, { method: 'POST' })

      const poll = setInterval(async () => {
        try {
          const prog = await fetchApi(`/rfps/${rfpId}/generation-progress`)
          setProgress({ 
            current: prog.current, 
            total: prog.total, 
            statusMsg: prog.status_message,
            lastActivity: prog.last_activity,
            generation_mode: prog.generation_mode,
            generated_document: prog.generated_document,
            compliance_matrix: prog.compliance_matrix,
            status: prog.status,
            is_complete: prog.is_complete
          })
          const names = new Set<string>()
          const sections = getSectionsForMode(prog.generation_mode)
          sections.slice(0, prog.current).forEach(s => names.add(s.name))
          setGeneratedSections(names)
          if (prog.status === 'completed' || prog.status === 'cancelled' || prog.status === 'failed' || prog.status === 'paused' || prog.is_complete) {
            clearInterval(poll)
            setIsRegenerating(false)
            loadData()
          }
        } catch { clearInterval(poll); setIsRegenerating(false) }
      }, 5000)
    } catch {
      setIsRegenerating(false)
    }
  }

  const handleResume = async () => {
    if (isRegenerating) return
    setIsRegenerating(true)
    try {
      const { fetchApi } = await import('@/lib/api')
      await fetchApi(`/rfps/${rfpId}/resume-generation`, { method: 'POST' })
      showToast('Resuming generation...', 'success')

      const poll = setInterval(async () => {
        try {
          const prog = await fetchApi(`/rfps/${rfpId}/generation-progress`)
          setProgress({ 
            current: prog.current, 
            total: prog.total, 
            statusMsg: prog.status_message,
            lastActivity: prog.last_activity,
            generation_mode: prog.generation_mode,
            generated_document: prog.generated_document,
            compliance_matrix: prog.compliance_matrix,
            status: prog.status,
            is_complete: prog.is_complete
          })
          const names = new Set<string>()
          const sections = getSectionsForMode(prog.generation_mode)
          sections.slice(0, prog.current).forEach(s => names.add(s.name))
          setGeneratedSections(names)
          if (prog.status === 'completed' || prog.status === 'cancelled' || prog.status === 'failed' || prog.status === 'paused' || prog.is_complete) {
            clearInterval(poll)
            setIsRegenerating(false)
            loadData()
          }
        } catch { clearInterval(poll); setIsRegenerating(false) }
      }, 5000)
    } catch {
      setIsRegenerating(false)
      showToast('Resume failed', 'error')
    }
  }

  const handleSendMessage = async (preset?: string) => {
    const msg = preset || chatInput
    if (!msg.trim() || isChatLoading) return
    setMessages(prev => [...prev, { role: 'user', text: msg }])
    setChatInput('')
    setIsChatLoading(true)
    try {
      const { fetchApi } = await import('@/lib/api')
      const data = await fetchApi(`/rfps/${rfpId}/chat`, {
        method: 'POST',
        body: JSON.stringify({ message: msg, knowledge_mode: knowledgeMode })
      })
      setMessages(prev => [...prev, { role: 'ai', text: data.reply }])
    } catch {
      setMessages(prev => [...prev, { role: 'ai', text: 'AI Assistant unavailable. Please try again.' }])
    } finally { setIsChatLoading(false) }
  }

  const isDrafting = rfp?.current_status === 'generating_draft' || rfp?.current_status === 'in_drafting'
  const currentSections = getSectionsForMode(progress?.generation_mode)
  const isDraftReady = progress?.is_complete || !!progress?.generated_document || (progress?.current || 0) >= currentSections.length || ["draft_complete", "ai_draft_ready", "pending-review", "submitted_for_review", "final_approved"].includes(rfp?.current_status)
  const progressPct = progress ? Math.round((progress.current / (progress.total || 1)) * 100) : 0
  
  // Resume conditions: 
  const isStalled = progress && progress.current < progress.total && progress.lastActivity && (new Date().getTime() - new Date(progress.lastActivity).getTime() > 180000);
  const isPaused = rfp?.current_status === 'generation_paused' || rfp?.current_status?.includes('quota') || rfp?.current_status?.includes('rate-limit');
  const showResume = (isPaused || isStalled) && !isDraftReady && !isDrafting;

  if (loading) {
    return (
      <div className="space-y-4 animate-pulse p-8">
        <div className="h-7 w-48 bg-zinc-100 rounded" />
        <div className="grid grid-cols-2 gap-4">
          <div className="h-24 bg-zinc-100 rounded-xl" />
          <div className="h-24 bg-zinc-100 rounded-xl" />
        </div>
        <div className="h-64 bg-zinc-100 rounded-xl" />
      </div>
    )
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
        <div className="space-y-1.5">
          <button onClick={() => router.back()} className="group flex items-center gap-1.5 text-[10px] font-bold text-zinc-400 hover:text-zinc-900 mb-1 transition-colors uppercase tracking-widest">
            <ChevronLeft className="w-3 h-3 group-hover:-translate-x-0.5 transition-transform" /> Back
          </button>
          <h1 className="text-xl lg:text-2xl font-bold text-zinc-900 tracking-tight leading-tight truncate max-w-lg">
            {rfp?.title || 'Loading Workspace...'}
          </h1>
          <div className="flex items-center gap-2.5">
            <Badge variant="outline" className="h-5 px-1.5 text-[9px] font-black uppercase tracking-wider bg-zinc-100/50 border-zinc-200/60 text-zinc-500">SA Workspace</Badge>
            <span className="w-1 h-1 bg-zinc-300 rounded-full" />
            <span className="text-[10px] font-bold text-indigo-600 uppercase tracking-widest">
              Mode: {progress?.generation_mode?.toUpperCase() || 'STANDARD'}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2.5 flex-wrap">
          {showResume && (
            <Button
              onClick={handleResume}
              disabled={isRegenerating}
              className="h-9 px-4 text-[11px] font-bold bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 shadow-md shadow-emerald-100 transition-all active:scale-95 disabled:opacity-50"
            >
              <RefreshCw className={cn('w-3.5 h-3.5 mr-2', isRegenerating && 'animate-spin')} />
              Resume Generation
            </Button>
          )}
          {!isDrafting && (
            <Button
              variant="outline"
              onClick={handleRegenerate}
              disabled={isRegenerating}
              className="h-9 px-4 text-[11px] font-bold border-zinc-200 rounded-lg text-zinc-600 hover:bg-zinc-50 bg-white transition-all active:scale-95 disabled:opacity-50"
            >
              <RefreshCw className={cn('w-3.5 h-3.5 mr-2', isRegenerating && 'animate-spin')} />
              Regenerate
            </Button>
          )}
          <Button
            onClick={handleSubmitForReview}
            disabled={isSubmitting || rfp?.current_status === 'submitted_for_review' || !isDraftReady}
            className="h-9 px-5 text-[11px] font-bold bg-zinc-900 text-white rounded-lg hover:bg-zinc-800 transition-all active:scale-95 disabled:opacity-50 shadow-lg shadow-zinc-900/10"
          >
            <Send className="w-3.5 h-3.5 mr-2" />
            {isSubmitting ? 'Submitting...' : rfp?.current_status === 'submitted_for_review' ? 'Submitted' : 'Submit Review'}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        {/* Left 8/12: Document Cards + TOC */}
        <div className="xl:col-span-8 space-y-6">
          {/* Document Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {/* Original RFP */}
            <div className="premium-card p-4 flex flex-col justify-between group relative overflow-hidden bg-white">
              <div className="flex items-start justify-between mb-4">
                <div className="w-9 h-9 rounded-xl bg-zinc-50 border border-zinc-100 flex items-center justify-center shrink-0">
                  <FileText className="w-4.5 h-4.5 text-zinc-400" />
                </div>
                <a
                  href={`${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'}/uploads/rfp/${rfpId}/download`}
                  target="_blank" rel="noreferrer"
                  className="p-1.5 rounded-lg text-zinc-300 hover:text-zinc-900 hover:bg-zinc-100 transition-all"
                >
                  <Download className="w-4 h-4" />
                </a>
              </div>
              <div>
                <p className="text-[9px] font-bold uppercase tracking-widest text-zinc-400 mb-1">Source RFP</p>
                <p className="text-[13px] font-bold text-zinc-900 truncate leading-tight">
                  {rfp?.file_name || 'Original RFP'}
                </p>
              </div>
            </div>

            {/* AI Draft */}
            <div className={cn(
              'premium-card p-4 flex flex-col justify-between group relative overflow-hidden',
              isDraftReady ? 'bg-indigo-50/30 border-indigo-100/50' : 'bg-white'
            )}>
              <div className="flex items-start justify-between mb-4">
                <div className={cn('w-9 h-9 rounded-xl border flex items-center justify-center shrink-0', isDraftReady ? 'bg-indigo-100 border-indigo-200 text-indigo-600' : 'bg-zinc-50 border-zinc-100 text-zinc-400')}>
                  <Sparkles className="w-4.5 h-4.5" />
                </div>
                {isDraftReady && (
                  <a
                    href={progress?.generated_document ? `${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'}/rfps/${rfpId}/download-generated/${progress.generated_document.file_name}` : `${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'}/rfps/${rfpId}/export`}
                    target="_blank" rel="noreferrer"
                    className="p-1.5 rounded-lg text-indigo-400 hover:text-indigo-900 hover:bg-indigo-100 transition-all"
                  >
                    <Download className="w-4 h-4" />
                  </a>
                )}
              </div>
              <div className="min-w-0">
                <p className="text-[9px] font-bold uppercase tracking-widest text-zinc-400 mb-1">Generated Draft</p>
                {isDrafting && progress ? (
                  <div className="space-y-2">
                    <div className="flex justify-between text-[10px] font-black uppercase tracking-tighter">
                      <span className="text-indigo-600 animate-pulse">Processing...</span>
                      <span className="text-zinc-900">{progressPct}%</span>
                    </div>
                    <div className="w-full bg-zinc-100 h-1 rounded-full overflow-hidden">
                      <div className="bg-indigo-600 h-full rounded-full transition-all duration-700" style={{ width: `${progressPct}%` }} />
                    </div>
                  </div>
                ) : (
                  <p className={cn('text-[13px] font-bold truncate leading-tight', isDraftReady ? 'text-indigo-900' : 'text-zinc-400')}>
                    {isDraftReady ? (progress?.generated_document?.file_name || 'Draft_Response_v1.docx') : 'Draft pending...'}
                  </p>
                )}
              </div>
            </div>

            {/* Compliance Matrix */}
            <div className={cn(
              'premium-card p-4 flex flex-col justify-between group relative overflow-hidden',
              isDraftReady ? 'bg-emerald-50/30 border-emerald-100/50' : 'bg-white'
            )}>
              <div className="flex items-start justify-between mb-4">
                <div className={cn('w-9 h-9 rounded-xl border flex items-center justify-center shrink-0', 
                  isDraftReady ? 'bg-emerald-100 border-emerald-200 text-emerald-600' : 'bg-zinc-50 border-zinc-100 text-zinc-400'
                )}>
                  <TableProperties className="w-4.5 h-4.5" />
                </div>
                {progress?.compliance_matrix ? (
                  <a
                    href={`${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'}/rfps/${rfpId}/download-generated/${progress.compliance_matrix.file_name}`}
                    target="_blank" rel="noreferrer"
                    className="p-1.5 rounded-lg text-emerald-400 hover:text-emerald-900 hover:bg-emerald-100 transition-all"
                  >
                    <Download className="w-4 h-4" />
                  </a>
                ) : isDraftReady && progress?.generation_mode !== 'short' && (
                  <button
                    onClick={async () => {
                      try {
                        const { fetchApi } = await import('@/lib/api')
                        await fetchApi(`/rfps/${rfpId}/export-compliance-matrix`, { method: 'POST' })
                        showToast('Compliance Matrix generated successfully')
                        // Trigger a progress refresh
                        const data = await fetchApi(`/rfps/${rfpId}/generation-progress`)
                        setProgress(data)
                      } catch (err) {
                        showToast('Failed to generate compliance matrix', 'error')
                      }
                    }}
                    className="p-1.5 rounded-lg text-zinc-400 hover:text-emerald-600 hover:bg-emerald-50 transition-all"
                    title="Generate Compliance Matrix"
                  >
                    <RefreshCw className="w-4 h-4" />
                  </button>
                )}
              </div>
              <div className="min-w-0">
                <p className="text-[9px] font-bold uppercase tracking-widest text-zinc-400 mb-1">Compliance View</p>
                <div className="flex flex-col">
                  <p className={cn('text-[13px] font-bold truncate leading-tight', isDraftReady ? 'text-emerald-900' : 'text-zinc-400')}>
                    {progress?.compliance_matrix 
                      ? progress.compliance_matrix.file_name 
                      : progress?.generation_mode === 'short' 
                        ? 'Compliance Summary' 
                        : 'Compliance_Matrix.docx'}
                  </p>
                  <p className="text-[10px] font-medium text-zinc-500 mt-1">
                    {progress?.compliance_matrix 
                      ? 'Ready for download' 
                      : progress?.generation_mode === 'short' 
                        ? 'Included in proposal' 
                        : isDraftReady ? 'Not generated yet' : 'Extracting...'}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* TOC Panel */}
          <div className="premium-card bg-white p-0 overflow-hidden">
             <div className="px-5 py-3.5 border-b border-zinc-100 bg-zinc-50/30 flex items-center justify-between">
                <h3 className="text-[11px] font-bold text-zinc-400 uppercase tracking-widest">Proposal Architecture ({progress?.generation_mode?.toUpperCase() || 'STANDARD'})</h3>
                <span className="text-[10px] font-bold text-zinc-900 bg-zinc-100 px-2 py-0.5 rounded-full">{generatedSections.size}/{currentSections.length} Sections</span>
             </div>
             <div className="p-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-1 max-h-[400px] overflow-y-auto">
                {currentSections.map(sec => {
                  const isGenerated = generatedSections.has(sec.name)
                  return (
                    <div key={sec.order} className="flex items-center gap-3 py-2 border-b border-zinc-50 group">
                      <div className={cn('w-5 h-5 rounded-lg flex items-center justify-center shrink-0 text-[9px] font-black transition-all', 
                        isGenerated ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-200' : 'bg-zinc-100 text-zinc-400 group-hover:bg-zinc-200'
                      )}>
                        {isGenerated ? <CheckCircle2 className="w-3 h-3" /> : sec.order}
                      </div>
                      <span className={cn('text-[12px] truncate transition-colors', isGenerated ? 'font-bold text-zinc-900' : 'font-medium text-zinc-400')}>
                        {sec.name}
                      </span>
                    </div>
                  )
                })}
             </div>
          </div>

          {/* Draft Quality Status */}
          <div className="premium-card bg-white p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-[11px] font-bold text-zinc-400 uppercase tracking-widest">Post-Generation Verification</h3>
                <p className="text-[12px] font-medium text-zinc-500 mt-1">Automated validation of structure, compliance, and formatting</p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={async () => {
                  try {
                    const { fetchApi } = await import('@/lib/api')
                    const q = await fetchApi(`/rfps/${rfpId}/quality-check`, { method: 'POST' })
                    setQuality(q)
                    showToast('Quality metrics updated')
                  } catch { showToast('Check failed', 'error') }
                }}
                className="h-8 text-[10px] font-black uppercase tracking-widest bg-zinc-50 border-zinc-200 hover:bg-zinc-900 hover:text-white transition-all px-4 rounded-lg"
              >
                {quality?.is_final_check ? 'Recalibrate Metrics' : 'Run Quality Audit'}
              </Button>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: 'Structure',          ok: quality?.structure?.passed,           val: '100%' },
                { label: 'Artifacts',          ok: quality?.placeholders?.passed,        val: 'No Gaps' },
                { label: 'TOC Sync',           ok: quality?.toc?.passed,                val: 'Aligned' },
                { label: 'Empty Sect.',        ok: quality?.empty_sections?.passed,      val: 'Zero' },
                { label: 'Formatting',         ok: quality?.malformed_tables?.passed,   val: 'Clean' },
                { label: 'Expansion',          ok: quality?.expansion?.passed,          val: quality?.expansion?.ratio ? `${quality.expansion.ratio.toFixed(1)}x` : 'Ideal' },
                { label: 'Client Name',        ok: quality?.client_check?.passed,       val: 'Detected' },
                { label: 'Headings',           ok: quality?.duplicate_headings?.passed, val: 'Unique' },
              ].map((check, i) => (
                <div key={i} className={cn('p-3 rounded-xl border flex flex-col gap-1', 
                  check.ok ? 'bg-emerald-50/40 border-emerald-100' : 'bg-amber-50/40 border-amber-100'
                )}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-tighter">{check.label}</span>
                    {check.ok ? <CheckCircle2 className="w-3 h-3 text-emerald-500" /> : <AlertTriangle className="w-3 h-3 text-amber-500" />}
                  </div>
                  <span className={cn('text-[13px] font-black', check.ok ? 'text-zinc-900' : 'text-amber-700')}>
                    {check.ok ? check.val : 'Review'}
                  </span>
                </div>
              ))}

            </div>
          </div>
        </div>

        {/* Right 4/12: AI Assistant */}
        <div className="xl:col-span-4">
          <Card className="premium-card border-none bg-white sticky top-20 shadow-xl shadow-zinc-200/50">
            <CardHeader className="p-4 border-b border-zinc-100 bg-zinc-50/30">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-zinc-900 flex items-center justify-center shadow-lg shadow-zinc-900/20">
                    <Sparkles className="w-4 h-4 text-white" />
                  </div>
                  <div>
                    <CardTitle className="text-[13px] font-black text-zinc-900 tracking-tight">Technical Assistant</CardTitle>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <div className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
                      <span className="text-[9px] font-black text-indigo-600 uppercase tracking-widest">System Ready</span>
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
              <div className="h-[380px] overflow-y-auto p-4 space-y-4 bg-zinc-50/20 scroll-smooth">
                {messages.map((m, i) => (
                  <div key={i} className={cn('flex flex-col animate-in fade-in slide-in-from-bottom-1 duration-300', m.role === 'ai' ? 'items-start' : 'items-end')}>
                    <div className={cn(
                      'max-w-[90%] px-4 py-2.5 text-[13px] leading-relaxed rounded-2xl shadow-sm',
                      m.role === 'ai'
                        ? 'bg-white border border-zinc-100 text-zinc-700 rounded-tl-none font-medium'
                        : 'bg-zinc-900 text-white rounded-tr-none font-bold'
                    )}>
                      {m.text}
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
                  {['Technical Gaps', 'Validation', 'Summarize Section'].map((p, i) => (
                    <button key={i} onClick={() => handleSendMessage(p)}
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
                    placeholder="Describe technical requirement..."
                    className="w-full min-h-[90px] p-3.5 text-xs font-bold border border-zinc-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-zinc-900/5 focus:border-zinc-900 transition-all resize-none bg-zinc-50/50 placeholder:text-zinc-400 placeholder:font-medium"
                  />
                  <Button onClick={() => handleSendMessage()} disabled={!chatInput.trim() || isChatLoading}
                    className="absolute bottom-2.5 right-2.5 h-8 w-8 p-0 bg-zinc-900 hover:bg-zinc-800 text-white rounded-lg transition-all active:scale-90 disabled:opacity-30 shadow-lg shadow-zinc-900/20">
                    <Send className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}

export default function WorkspaceDetail() {
  return (
    <Suspense fallback={<div className="animate-pulse space-y-4"><div className="h-8 w-48 bg-zinc-100 rounded" /><div className="h-64 bg-zinc-100 rounded-xl" /></div>}>
      <WorkspaceContent />
    </Suspense>
  )
}
