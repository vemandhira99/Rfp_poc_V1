/**
 * statusUtils.ts
 * ──────────────
 * Frontend status mapping.
 * Never shows raw backend status strings to business users.
 */

type StatusInfo = {
  label: string
  badgeClass: string
  isPulsing: boolean
  canRetry?: boolean    // Show "Retry" button
  canResume?: boolean   // Show "Resume" button
}

const STATUS_MAP: Record<string, StatusInfo> = {
  // Upload / Analysis
  uploaded:              { label: 'Uploaded',               badgeClass: 'bg-blue-50 text-blue-700 border-blue-200',       isPulsing: false },
  queued_for_processing: { label: 'Analysis Running',       badgeClass: 'bg-blue-50 text-blue-600 border-blue-200',       isPulsing: true  },
  analysis_queued:       { label: 'Analysis Running',       badgeClass: 'bg-blue-50 text-blue-600 border-blue-200',       isPulsing: true  },
  parsing:               { label: 'Parsing Document',       badgeClass: 'bg-blue-50 text-blue-600 border-blue-200',       isPulsing: true  },
  parsed:                { label: 'Analysis Running',       badgeClass: 'bg-blue-50 text-blue-600 border-blue-200',       isPulsing: true  },
  processing_summary:    { label: 'Analysis Running',       badgeClass: 'bg-blue-50 text-blue-600 border-blue-200',       isPulsing: true  },
  analyzing_structure:   { label: 'Analysis Running',       badgeClass: 'bg-blue-50 text-blue-600 border-blue-200',       isPulsing: true  },
  extracting_metrics:    { label: 'Analysis Running',       badgeClass: 'bg-blue-50 text-blue-600 border-blue-200',       isPulsing: true  },
  finalizing_insights:   { label: 'Analysis Running',       badgeClass: 'bg-blue-50 text-blue-600 border-blue-200',       isPulsing: true  },

  // Analysis done / awaiting PM
  summary_generated:     { label: 'Ready for PM Review',   badgeClass: 'bg-indigo-50 text-indigo-700 border-indigo-200', isPulsing: false },
  ready_for_pm_review:   { label: 'Ready for PM Review',   badgeClass: 'bg-indigo-50 text-indigo-700 border-indigo-200', isPulsing: false },
  analysis_complete:     { label: 'Ready for PM Review',   badgeClass: 'bg-indigo-50 text-indigo-700 border-indigo-200', isPulsing: false },
  'pending-review':      { label: 'Ready for PM Review',   badgeClass: 'bg-indigo-50 text-indigo-700 border-indigo-200', isPulsing: false },
  under_review:          { label: 'Under PM Review',       badgeClass: 'bg-amber-50 text-amber-700 border-amber-200',   isPulsing: false },
  awaiting_ceo_decision: { label: 'Needs PM Decision',     badgeClass: 'bg-amber-50 text-amber-700 border-amber-200',   isPulsing: false },

  // PM decisions
  approved:              { label: 'Approved by PM',        badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-200', isPulsing: false },
  rejected:              { label: 'Rejected',              badgeClass: 'bg-red-50 text-red-700 border-red-200',            isPulsing: false },
  on_hold:               { label: 'On Hold',               badgeClass: 'bg-zinc-100 text-zinc-600 border-zinc-200',        isPulsing: false },
  'on-hold':             { label: 'On Hold',               badgeClass: 'bg-zinc-100 text-zinc-600 border-zinc-200',        isPulsing: false },

  // Assignment
  assigned_to_sa:        { label: 'Assigned to Architect', badgeClass: 'bg-indigo-50 text-indigo-600 border-indigo-200',  isPulsing: false },

  // Generation (PART 3: Human approval gate confirmed)
  generation_confirmed:  { label: 'Generation Queued',     badgeClass: 'bg-purple-50 text-purple-600 border-purple-200',  isPulsing: true  },
  generating_draft:      { label: 'Draft In Progress',     badgeClass: 'bg-purple-50 text-purple-600 border-purple-200',  isPulsing: true  },
  in_drafting:           { label: 'Draft In Progress',     badgeClass: 'bg-purple-50 text-purple-600 border-purple-200',  isPulsing: true  },

  // Draft ready / submitted
  ai_draft_ready:        { label: 'AI Draft Ready',        badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-200', isPulsing: false },
  draft_complete:        { label: 'AI Draft Ready',        badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-200', isPulsing: false },
  under_sa_review:       { label: 'SA Review',             badgeClass: 'bg-amber-50 text-amber-700 border-amber-200',     isPulsing: false },
  submitted_for_review:  { label: 'Submitted for PM Review', badgeClass: 'bg-indigo-50 text-indigo-700 border-indigo-200', isPulsing: false },
  revision_requested:    { label: 'Revision Requested',   badgeClass: 'bg-orange-50 text-orange-700 border-orange-200',  isPulsing: false },
  final_approved:        { label: 'Final Approved ✓',      badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-200', isPulsing: false },
  finalized:             { label: 'Final Output Ready',    badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-200', isPulsing: false },

  // PART 5: Paused / Needs Attention — with resume/retry actions
  paused:                { label: 'Paused — Resume Available', badgeClass: 'bg-amber-50 text-amber-700 border-amber-300', isPulsing: false, canResume: true },
  generation_paused:     { label: 'Draft Paused',         badgeClass: 'bg-amber-50 text-amber-700 border-amber-300',    isPulsing: false, canResume: true },
  failed_retryable:      { label: 'Needs Attention',      badgeClass: 'bg-rose-50 text-rose-700 border-rose-200',       isPulsing: false, canRetry: true  },
  failed_final:          { label: 'Failed',               badgeClass: 'bg-red-50 text-red-700 border-red-200',          isPulsing: false },

  // Evaluator flags (PART 4)
  needs_human_review:    { label: 'Review Required',      badgeClass: 'bg-orange-50 text-orange-700 border-orange-200', isPulsing: false },

  // Legacy error states — mapped to clean messages
  error:                 { label: 'Needs Attention',      badgeClass: 'bg-rose-50 text-rose-700 border-rose-200',       isPulsing: false, canRetry: true },
  rate_limit_error:      { label: 'Paused — Retry Later', badgeClass: 'bg-amber-50 text-amber-700 border-amber-300',    isPulsing: false, canRetry: true },
  quota_exceeded:        { label: 'Paused — Retry Later', badgeClass: 'bg-amber-50 text-amber-700 border-amber-300',    isPulsing: false, canRetry: true },
  failed:                { label: 'Needs Attention',      badgeClass: 'bg-rose-50 text-rose-700 border-rose-200',       isPulsing: false, canRetry: true },

  // MVP: Document Quality States
  needs_more_detail:     { label: 'Needs More Detail',    badgeClass: 'bg-amber-50 text-amber-700 border-amber-200',   isPulsing: false },
  insufficient_rfp_detail: { label: 'Limited RFP Detail', badgeClass: 'bg-amber-50 text-amber-700 border-amber-200',   isPulsing: false },
  uploaded_insufficient_detail: { label: 'Needs More Detail', badgeClass: 'bg-amber-50 text-amber-700 border-amber-200', isPulsing: false },
  extraction_needs_review: { label: 'Extraction Needs Review', badgeClass: 'bg-amber-50 text-amber-700 border-amber-200', isPulsing: false },
  extraction_failed_or_scanned_pdf: { label: 'Extraction Issue', badgeClass: 'bg-amber-50 text-amber-700 border-amber-200', isPulsing: false },
}

const DEFAULT: StatusInfo = {
  label: 'Processing',
  badgeClass: 'bg-zinc-50 text-zinc-600 border-zinc-200',
  isPulsing: false,
}

export function getStatusInfo(internalStatus: string | undefined | null, documentQuality?: string | null): StatusInfo {
  // Logic Override: If backend flags insufficient detail, prioritize that visibility
  if (documentQuality === 'insufficient_rfp_detail') {
    return STATUS_MAP['needs_more_detail']
  }
  if (documentQuality === 'extraction_failed_or_scanned_pdf' || internalStatus === 'extraction_needs_review') {
    return STATUS_MAP['extraction_needs_review']
  }

  if (!internalStatus) return DEFAULT
  const key = internalStatus.toLowerCase().trim()
  return STATUS_MAP[key] ?? DEFAULT
}

export function getStatusLabel(internalStatus: string | undefined | null): string {
  return getStatusInfo(internalStatus).label
}

export function canRetryStatus(internalStatus: string | undefined | null): boolean {
  return getStatusInfo(internalStatus).canRetry ?? false
}

export function canResumeStatus(internalStatus: string | undefined | null): boolean {
  return getStatusInfo(internalStatus).canResume ?? false
}

export function formatValue(val: string | number | null | undefined): string {
  if (!val) return 'Value TBD'
  const str = String(val)
  if (str === '₹0' || str === '$0' || str === '0') return 'Value TBD'
  return str
}

export function formatClient(client: string | null | undefined): string {
  if (!client || client === 'Unknown' || client === 'unknown' || client === '') return 'Client TBD'
  return client
}

export function formatDeadline(deadline: string | null | undefined): string {
  if (!deadline || deadline === 'TBD' || deadline === 'null') return 'Deadline TBD'
  return deadline
}

export function formatEffortShort(effort: string | null | undefined): string {
  if (!effort) return ''
  // Extract number if format is "X person-months" or similar
  const match = effort.match(/(\d+)\s*(person-months?|months?|weeks?|days?)/i)
  if (match) return `${match[1]} ${match[2]}`
  if (effort.length > 20) return effort.substring(0, 20) + '…'
  return effort
}

