"""
generation_service.py
---------------------
Batch-based proposal generation engine.
- Generic template (not CBSE/NAD specific)
- 10 controlled batches instead of 40 individual sections
- Configurable length modes: short / standard / full
- No duplicate sections
- Background-safe (uses its own DB session)
"""
import json
import time
import re
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.rfp import RFPDocument, RFPDraft, AuditLog
from app.services.ai_service import gemini_client, call_gemini_with_retry, ensure_gemini_file, clean_json

# ─────────────────────────────────────────────────────────────────────────────
# Generic Proposal Table of Contents (works for ANY RFP type)
# ─────────────────────────────────────────────────────────────────────────────
PROPOSAL_SECTIONS_STANDARD = [
    {"order": 1,  "name": "Executive Summary",                         "batch": 1},
    {"order": 2,  "name": "Understanding of RFP Requirements",         "batch": 1},
    {"order": 3,  "name": "Proposed Solution Overview",                "batch": 2},
    {"order": 4,  "name": "System Architecture",                       "batch": 2},
    {"order": 5,  "name": "Functional Solution Architecture",          "batch": 3},
    {"order": 6,  "name": "User Roles and Workflow Coverage",          "batch": 3},
    {"order": 7,  "name": "Integration Architecture",                  "batch": 4},
    {"order": 8,  "name": "Data Migration Strategy",                   "batch": 4},
    {"order": 9,  "name": "Implementation Strategy and Timeline",      "batch": 5},
    {"order": 10, "name": "Project Governance and Resource Deployment", "batch": 5},
    {"order": 11, "name": "Testing and Quality Assurance Strategy",    "batch": 6},
    {"order": 12, "name": "Training and Change Management",            "batch": 6},
    {"order": 13, "name": "Operations and Maintenance Strategy",       "batch": 7},
    {"order": 14, "name": "Service Level Agreements and KPIs",         "batch": 7},
    {"order": 15, "name": "Security and Compliance Framework",         "batch": 8},
    {"order": 16, "name": "Risk Management and Mitigation Strategy",   "batch": 8},
    {"order": 17, "name": "Conclusion",                                "batch": 9},
    {"order": 18, "name": "Annexure 1 - Compliance Matrix",            "batch": 10},
    {"order": 19, "name": "Annexure 2 - Technical Architecture",       "batch": 10},
    {"order": 20, "name": "Annexure 3 - Implementation Plan and Team", "batch": 10},
]

PROPOSAL_SECTIONS_SHORT = [
    {"order": 1,  "name": "Executive Summary",                         "batch": 1},
    {"order": 2,  "name": "Understanding of RFP",                      "batch": 1},
    {"order": 3,  "name": "Proposed Solution Overview",                "batch": 2},
    {"order": 4,  "name": "Functional Coverage",                        "batch": 2},
    {"order": 5,  "name": "Technical Architecture",                     "batch": 3},
    {"order": 6,  "name": "Integration Approach",                      "batch": 3},
    {"order": 7,  "name": "Data Migration Approach",                   "batch": 4},
    {"order": 8,  "name": "Implementation Plan",                       "batch": 4},
    {"order": 9,  "name": "Testing and Quality",                       "batch": 5},
    {"order": 10, "name": "Security and Compliance",                   "batch": 5},
    {"order": 11, "name": "SLA / O&M",                                 "batch": 6},
    {"order": 12, "name": "Risk and Mitigation",                       "batch": 6},
    {"order": 13, "name": "Compliance Summary",                        "batch": 7},
    {"order": 14, "name": "Conclusion",                                "batch": 7},
]

PROPOSAL_SECTIONS_FULL = PROPOSAL_SECTIONS_STANDARD + [
    {"order": 21, "name": "Annexure 4 - Case Studies",                 "batch": 11},
    {"order": 22, "name": "Annexure 5 - Resumes of Key Personnel",     "batch": 11},
]

PROPOSAL_SECTIONS_TINY = [
    {"order": 1,  "name": "Executive Summary",                         "batch": 1},
    {"order": 2,  "name": "Brief Concept Note",                        "batch": 1},
    {"order": 3,  "name": "Proposed Solution Overview",                "batch": 2},
    {"order": 4,  "name": "One-Page Response Summary",                 "batch": 2},
]


def get_sections_for_mode(mode: str):
    if mode == "short":
        return PROPOSAL_SECTIONS_SHORT
    if mode == "full":
        return PROPOSAL_SECTIONS_FULL
    if mode == "tiny":
        return PROPOSAL_SECTIONS_TINY
    return PROPOSAL_SECTIONS_STANDARD


PROPOSAL_SECTIONS = PROPOSAL_SECTIONS_STANDARD # Fallback for legacy calls
TOTAL_SECTIONS_STANDARD = len(PROPOSAL_SECTIONS_STANDARD)
TOTAL_SECTIONS_SHORT = len(PROPOSAL_SECTIONS_SHORT)

LENGTH_TARGETS = {
    "short": {
        "words_per_section": 500, 
        "max_words_per_section": 500,
        "label": "Short Draft (25-40 pages)", 
        "target_pages": "25-40",
        "max_words_total": 9000
    },
    "standard": {
        "words_per_section": 800, 
        "max_words_per_section": 900,
        "label": "Standard Draft (60-80 pages)", 
        "target_pages": "60-80",
        "max_words_total": 22000
    },
    "full": {
        "words_per_section": 1200, 
        "max_words_per_section": 1500,
        "label": "Full Proposal (90-120 pages)", 
        "target_pages": "90-120",
        "max_words_total": 35000
    },
    "tiny": {
        "words_per_section": 300, 
        "max_words_per_section": 400,
        "label": "Brief Response (2-5 pages)", 
        "target_pages": "2-5",
        "max_words_total": 1200
    },
}

DEFAULT_LENGTH_MODE = "short"  # Changed for E2E testing; restore to "standard" for production


# ─────────────────────────────────────────────────────────────────────────────
# RFP Intelligence Extraction
# ─────────────────────────────────────────────────────────────────────────────
def extract_rfp_intelligence(db: Session, rfp_id: int) -> dict:
    """
    Extract a normalized RFP Intelligence JSON from the uploaded document.
    This object is reused across all batches — avoids re-sending full text repeatedly.
    """
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp:
        return {}

    # Return cached intelligence if available
    if rfp.summary_json:
        try:
            cached = json.loads(rfp.summary_json)
            if cached.get("project_title") or cached.get("title"):
                return cached
        except Exception:
            pass

    prompt = """
You are an expert RFP analyst. Analyze the provided RFP document and extract a precise intelligence summary.

Return ONLY this JSON structure with no additional text or markdown:
{
  "project_title": "exact project title from document",
  "client_name": "client or organization name",
  "client_type": "Government / Enterprise / Public Sector / Private",
  "scope_summary": "2-3 sentence project scope",
  "submission_deadline": "YYYY-MM-DD or TBD",
  "contract_value": "amount with currency or TBD",
  "contract_duration": "duration or TBD",
  "payment_terms": "payment terms or TBD",
  "effort_estimation": "estimated person-months or TBD",
  "win_probability": 70,
  "complexity_score": 7,
  "recommended_action": "Proceed / Hold / Reject",
  "recommendation_reason": "brief reason",
  "go_no_go": "GO or NO-GO",
  "executive_summary": "professional 3-4 sentence summary",
  "next_steps": "recommended immediate actions",
  "functional_requirements": ["req1", "req2", "req3"],
  "non_functional_requirements": ["nfr1", "nfr2"],
  "integration_requirements": ["int1", "int2"],
  "security_requirements": ["sec1", "sec2"],
  "sla_requirements": ["sla1", "sla2"],
  "eligibility_requirements": ["elig1"],
  "evaluation_criteria": ["crit1", "crit2"],
  "risks": [{"risk": "description", "severity": "high/medium/low"}],
  "mandatory_clauses": ["clause1", "clause2"],
  "deliverables": ["del1", "del2"],
  "implementation_timeline": "timeline summary",
  "support_period": "support duration",
  "key_requirements": ["req1", "req2", "req3"]
}
"""
    try:
        file_ref = ensure_gemini_file(db, rfp)
        if not file_ref:
            return {}
        response = call_gemini_with_retry(db=db, content=[file_ref, prompt])
        result = clean_json(response.text)
        if result:
            # Cache it as summary_json
            rfp.summary_json = json.dumps(result)
            db.add(AuditLog(rfp_id=rfp_id, action="rfp_intelligence_extracted", new_value=rfp.summary_json))
            db.commit()
            # PART 1: Also store into dedicated intelligence fields for 2-3 week persistence
            try:
                from app.services.context_service import extract_and_store_intelligence
                extract_and_store_intelligence(rfp_id, result, db)
            except Exception as ise:
                print(f"[generation_service] Intelligence field storage failed (non-fatal): {ise}")
            return result
    except Exception as e:
        print(f"[generation_service] Intelligence extraction failed for RFP {rfp_id}: {e}")
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# Single Section Generator
# ─────────────────────────────────────────────────────────────────────────────
def generate_section(
    db: Session,
    rfp: RFPDocument,
    section_name: str,
    section_order: int,
    version: int,
    rfp_intel: dict,
    length_mode: str = None,
    remaining_budget: int = None
) -> Optional[RFPDraft]:
    """Generate one proposal section using RFP context."""
    from app.config.company_profile import get_company_profile
    company = get_company_profile()
    
    mode = length_mode or DEFAULT_LENGTH_MODE
    target_config = LENGTH_TARGETS.get(mode, LENGTH_TARGETS[DEFAULT_LENGTH_MODE])
    word_target = target_config["words_per_section"]
    max_words = target_config["max_words_per_section"]
    
    if remaining_budget is not None:
        max_words = min(max_words, remaining_budget)
    
    # Special instructions for short mode annexures/summaries
    short_mode_extra = ""
    if mode == "short":
        if "Compliance Summary" in section_name:
            short_mode_extra = "\nNote: This is a high-level Compliance Summary. Summarize the key compliance points instead of a full matrix."
        elif "Technical Architecture" in section_name:
            short_mode_extra = "\nNote: Focus on Key Technical Architecture Notes. Be concise and use diagrams/bullet points where possible."
        elif "Implementation Plan" in section_name:
            short_mode_extra = "\nNote: Focus on Implementation Team Summary and high-level milestones."
            
    exec_summary_extra = ""
    if "Executive Summary" in section_name:
        exec_summary_extra = "\nNote: Structure the Executive Summary to be decision-friendly and concise (2-4 pages max). Include: 1) Client Problem, 2) Proposed Solution, 3) Expected Business Value, 4) Key Differentiators, 5) Delivery Confidence. Avoid excessive technical details."
    
    # Build context from extracted intelligence (not raw text)
    intel_summary = f"""
PROJECT: {rfp_intel.get('project_title', rfp.title)}
CLIENT: {rfp_intel.get('client_name', rfp.client_name or 'the client')}
CLIENT TYPE: {rfp_intel.get('client_type', 'Enterprise')}
SCOPE: {rfp_intel.get('scope_summary', '')}
DEADLINE: {rfp_intel.get('submission_deadline', 'TBD')}
CONTRACT VALUE: {rfp_intel.get('contract_value', 'TBD')}
CONTRACT DURATION: {rfp_intel.get('contract_duration', 'TBD')}
IMPLEMENTATION TIMELINE: {rfp_intel.get('implementation_timeline', 'TBD')}

KEY REQUIREMENTS:
{chr(10).join('- ' + r for r in rfp_intel.get('key_requirements', rfp_intel.get('functional_requirements', []))[:10])}

SLA REQUIREMENTS:
{chr(10).join('- ' + r for r in rfp_intel.get('sla_requirements', [])[:5])}

RISKS:
{chr(10).join('- ' + (r.get('risk','') + ' [' + r.get('severity','') + ']') for r in rfp_intel.get('risks', [])[:5])}
"""

    company_context = f"""
RESPONDING COMPANY:
- Legal Name: {company['company_legal_name']}
- Brand: {company['brand_name']}
- Platform: {company['product_name']}
- Overview: {company['company_overview']}
- Platform: {company['platform_description']}
- Certifications: {', '.join(company.get('certifications', []))}
"""

    prompt = f"""You are a Senior Management Consultant writing a professional enterprise RFP response proposal.

RFP INTELLIGENCE:
{intel_summary}

{company_context}

TASK: Write the complete content for this section of the proposal:

SECTION: {section_name}

RULES:
1. STRICT LIMIT: Write between {max(50, word_target - 100)} and {max_words} words. Do NOT exceed {max_words} words under any circumstances.
2. Use formal enterprise/government proposal language. Keep the tone controlled, specific, and evidence-oriented. Avoid marketing fluff or over-repetition.
3. Be specific to the client and project context above. Directly map to RFP requirements where possible.
4. Do NOT include the section title, section number, or "SECTION X:" in your output at all. Start directly with the content.
5. Do NOT use markdown headings unless absolutely required for deep sub-sections.
6. Include structured tables (using standard markdown pipe syntax) for mappings, requirements, or architecture components where useful.
7. Separate confirmed vs proposed capability. Use phrasing like "{company['brand_name']} proposes..." or "The solution shall support...". Do not use absolute claims unless verified.
8. Do NOT invent certifications, staff counts, or evidence. Mark uncertain claims as "To be validated".
9. Always refer to the responding company as "{company['company_legal_name']}" or "{company['brand_name']}"
10. Always refer to our platform as "{company['product_name']}" or "{company['platform_short_name']}"
11. Do NOT use placeholders like [Your Company Name], [Company Name], [Insert Name]
12. Do NOT repeat content from other sections. If already covered, briefly reference it.
13. {short_mode_extra if short_mode_extra else "Include specific technical details relevant to the project type"}
14. {exec_summary_extra}

Write the section content in raw markdown:"""

    try:
        file_ref = ensure_gemini_file(db, rfp)
        if file_ref:
            response = call_gemini_with_retry(db=db, content=[file_ref, prompt], task_name="draft_generation")
        else:
            response = call_gemini_with_retry(db=db, content=prompt, task_name="draft_generation")
        
        content = response.text.strip()
        if not content:
            return None
            
        # Sanitize text before storing
        content = sanitize_generated_text(content)
        
        # Strip duplicate heading from AI body
        content = strip_duplicate_section_heading(section_name, content, section_order)

        # ── PART 4: Evaluator-Optimizer Loop ─────────────────────────────────
        evaluation_status = "pending"
        evaluator_score = None
        evaluator_feedback = ""
        attempt_count = 1
        word_count = len(content.split())
        try:
            from app.services.evaluator_service import run_deterministic_checks, run_llm_evaluator
            det = run_deterministic_checks(content, section_name, mode, expected_title=section_name)
            word_count = det["word_count"]
            if det["passed"]:
                # Only run LLM evaluator if deterministic checks pass (saves tokens)
                rfp_context_for_eval = {
                    "client_name": rfp.client_name,
                    "executive_summary": rfp_intel.get("executive_summary"),
                    "risks": rfp_intel.get("risks"),
                }
                eval_res = run_llm_evaluator(content, section_name, rfp_context_for_eval, db)
                evaluator_score = eval_res["score"]
                evaluation_status = "passed" if eval_res["pass"] else "needs_human_review"
                evaluator_feedback = "; ".join(eval_res.get("issues", []))
            else:
                # Deterministic fail — mark for human review (no LLM call wasted)
                evaluation_status = "needs_human_review"
                evaluator_feedback = "; ".join(det["issues"])
        except Exception as eval_err:
            print(f"[generation_service] Evaluator failed for '{section_name}' (non-fatal): {eval_err}")
            evaluation_status = "pending"
        # ─────────────────────────────────────────────────────────────────────

        # Upsert section in DB
        existing = db.query(RFPDraft).filter(
            RFPDraft.rfp_id == rfp.id,
            RFPDraft.version == version,
            RFPDraft.section_name == section_name
        ).first()
        if existing:
            existing.draft_content = content
            existing.evaluation_status = evaluation_status
            existing.evaluator_score = evaluator_score
            existing.evaluator_feedback = evaluator_feedback
            existing.word_count = word_count
            existing.attempt_count = (existing.attempt_count or 0) + 1
            db.commit()
            db.refresh(existing)
            return existing

        draft = RFPDraft(
            rfp_id=rfp.id,
            section_name=section_name,
            section_order=section_order,
            version=version,
            draft_content=content,
            created_by=rfp.uploaded_by,
            evaluation_status=evaluation_status,
            evaluator_score=evaluator_score,
            evaluator_feedback=evaluator_feedback,
            word_count=word_count,
            attempt_count=1,
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
        return draft

    except Exception as e:
        db.rollback()
        print(f"[generation_service] Section '{section_name}' failed: {e}")
        raise e


def count_words(text: str) -> int:
    if not text: return 0
    return len(re.findall(r'\w+', text))

def sanitize_generated_text(text: str) -> str:
    """Removes invalid/broken characters and normalizes common technical terms."""
    if not text: return ""
    
    # Remove null bytes and other control chars (except newline/tab)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    
    # Remove specific broken unicode artifacts common in Gemini output
    text = text.replace('\uFFFE', '').replace('\uFFFF', '')
    text = text.replace('â€™', "'").replace('â€œ', '"').replace('â€', '"').replace('Ã¢', "'")
    
    # Normalize common tech terms if needed (POC requirement)
    text = re.sub(r'\blowcode\b', 'low-code', text, flags=re.IGNORECASE)
    text = re.sub(r'\bsemistructured\b', 'semi-structured', text, flags=re.IGNORECASE)
    
    return text.strip()

def strip_duplicate_section_heading(section_title: str, section_body: str, section_number: int) -> str:
    """Removes the first line(s) of body if they are just repeats of the section heading or "SECTION X:"."""
    if not section_body: return ""
    lines = section_body.split('\n')
    if not lines: return ""
    
    title_clean = section_title.strip().lower()
    
    # Remove empty lines at start
    while lines and not lines[0].strip():
        lines.pop(0)

    if not lines:
        return ""

    first_line = lines[0].strip().lower()
    
    # Patterns like "1. Executive Summary", "# Executive Summary", "Section 1: Executive Summary"
    # Also just "SECTION X:" alone
    patterns = [
        title_clean,
        f"{section_number}. {title_clean}",
        f"{section_number} {title_clean}",
        f"# {title_clean}",
        f"## {title_clean}",
        f"### {title_clean}",
        f"section {section_number}: {title_clean}",
        f"section {section_number} - {title_clean}",
        f"section {section_number}:",
        f"section {section_number}",
        f"# section {section_number}",
    ]
    
    if any(first_line.startswith(p) for p in patterns) or first_line == f"section {section_number}:":
        lines.pop(0)
        # Check second line just in case title was on the next line
        if lines and lines[0].strip().lower() == title_clean:
             lines.pop(0)

    return '\n'.join(lines).strip()


# ─────────────────────────────────────────────────────────────────────────────
# BUG 4 FIX: Repair Section Order for Existing Records
# ─────────────────────────────────────────────────────────────────────────────

# Canonical name-to-order mapping: covers all modes in one dict
_SECTION_ORDER_MAP = {}
for _sections in [PROPOSAL_SECTIONS_STANDARD, PROPOSAL_SECTIONS_SHORT, PROPOSAL_SECTIONS_FULL]:
    for _s in _sections:
        _SECTION_ORDER_MAP.setdefault(_s["name"].lower().strip(), _s["order"])

def repair_section_order(db: Session, rfp_id: int, version: int = None) -> int:
    """
    Repairs section_order for existing draft records that have NULL or wrong values.
    Maps known section titles back to their canonical order number.
    Returns count of records repaired.
    """
    query = db.query(RFPDraft).filter(RFPDraft.rfp_id == rfp_id)
    if version is not None:
        query = query.filter(RFPDraft.version == version)
    drafts = query.all()

    repaired = 0
    for draft in drafts:
        title_key = (draft.section_name or "").lower().strip()
        canonical_order = _SECTION_ORDER_MAP.get(title_key)
        if canonical_order and draft.section_order != canonical_order:
            draft.section_order = canonical_order
            repaired += 1
    if repaired:
        db.commit()
        print(f"[generation_service] repair_section_order: fixed {repaired} sections for RFP {rfp_id}")
    return repaired


def get_ordered_drafts(db: Session, rfp_id: int, version: int) -> list:
    """
    Always returns draft sections in deterministic section_order ASC.
    Repairs any wrong section_order values before returning.
    """
    repair_section_order(db, rfp_id, version)
    return db.query(RFPDraft).filter(
        RFPDraft.rfp_id == rfp_id,
        RFPDraft.version == version
    ).order_by(RFPDraft.section_order.asc()).all()

def compress_draft_if_needed(db: Session, rfp_id: int, version: int, max_words: int):
    """If total words exceed limit, summarize longest sections."""
    # BUG 4 FIX: Always ORDER BY section_order — never rely on unordered DB results
    drafts = db.query(RFPDraft).filter(
        RFPDraft.rfp_id == rfp_id, RFPDraft.version == version
    ).order_by(RFPDraft.section_order.asc()).all()
    total_words = sum(count_words(d.draft_content) for d in drafts)
    
    if total_words <= max_words:
        return
    
    print(f"[generation_service] Compressing draft: {total_words} > {max_words} limit")
    # Sort by length descending
    drafts.sort(key=lambda x: count_words(x.draft_content), reverse=True)
    
    # Simple compression: summarize top 3 longest sections if they are over 800 words
    for i in range(min(3, len(drafts))):
        d = drafts[i]
        if count_words(d.draft_content) > 800:
            prompt = f"Summarize the following proposal section to be roughly 20% shorter while keeping all key technical points and professional tone. Return ONLY the summarized markdown content.\n\nCONTENT:\n{d.draft_content}"
            response = call_gemini_with_retry(db=db, content=prompt, task_name="compression")
            if response and response.text:
                d.draft_content = response.text.strip()
    
    db.commit()

# ─────────────────────────────────────────────────────────────────────────────
# Main Background Generation Job
# ─────────────────────────────────────────────────────────────────────────────
def run_generation_job(rfp_id: int, length_mode: str = None):
    """
    Background generation job. Creates all proposal sections in batches.
    Updates generation_job table for frontend progress polling.
    PART 5: Integrated with job_service for heartbeat and recovery tracking.
    """
    db = SessionLocal()
    from app.services.ai_service import QuotaExhaustedError
    from app.services.job_service import create_job, update_job_heartbeat, complete_job, fail_job
    job = None
    try:
        rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
        if not rfp:
            print(f"[generation_service] RFP {rfp_id} not found")
            return

        if length_mode is None:
            from app.core.config import settings
            length_mode = getattr(settings, "DEFAULT_LENGTH_MODE", "short")

        # PART 5: Create tracked job for heartbeat monitoring
        job = create_job(db, rfp_id, "generation", total_steps=10)

        # Detect Tiny RFP
        doc_quality = "sufficient"
        if rfp.summary_json:
            try:
                sj = json.loads(rfp.summary_json)
                doc_quality = sj.get("document_quality", "sufficient")
            except: pass
            
        if doc_quality == "insufficient_rfp_detail":
            print(f"[generation_service] RFP {rfp_id} has insufficient detail. Overriding to 'tiny' mode.")
            length_mode = "tiny"

        rfp.generation_mode = length_mode
        rfp.current_status = "generating_draft"
        rfp.status_message = f"Starting {length_mode} proposal generation..."
        db.commit()


        # Determine version
        from sqlalchemy import desc
        latest = db.query(RFPDraft).filter(RFPDraft.rfp_id == rfp_id).order_by(desc(RFPDraft.version)).first()
        
        mode_sections = get_sections_for_mode(length_mode)
        target_total_sections = len(mode_sections)
        target_config = LENGTH_TARGETS.get(length_mode, LENGTH_TARGETS["short"])
        max_words_total = target_config["max_words_total"]

        if latest:
            existing_count = db.query(RFPDraft).filter(
                RFPDraft.rfp_id == rfp_id,
                RFPDraft.version == latest.version
            ).count()
            if existing_count >= target_total_sections:
                version = latest.version + 1
            else:
                version = latest.version
        else:
            version = 1

        print(f"[generation_service] Mode: {length_mode}")
        print(f"[generation_service] Target Page Range: {target_config['target_pages']}")
        print(f"[generation_service] Target Word Count: {max_words_total}")

        # Step 1: Extract RFP Intelligence
        rfp.status_message = "Extracting RFP intelligence..."
        db.commit()
        rfp_intel = extract_rfp_intelligence(db, rfp_id)
        
        # Group sections by batch
        batches: dict[int, list] = {}
        for s in mode_sections:
            b = s["batch"]
            if b not in batches:
                batches[b] = []
            batches[b].append(s)

        completed = 0
        total = target_total_sections

        for batch_num in sorted(batches.keys()):
            db.refresh(rfp)
            if rfp.current_status not in ["generating_draft", "in_drafting"]:
                print(f"[generation_service] Generation cancelled for RFP {rfp_id}")
                return

            batch_sections = batches[batch_num]
            max_batches = max(batches.keys()) if batches else 1
            rfp.status_message = f"Generating batch {batch_num}/{max_batches}: {batch_sections[0]['name']}..."
            db.commit()

            for section in batch_sections:
                db.refresh(rfp)
                if rfp.current_status not in ["generating_draft", "in_drafting"]:
                    return

                # Calculate current word count and remaining budget
                drafts = db.query(RFPDraft).filter(RFPDraft.rfp_id == rfp.id, RFPDraft.version == version).order_by(RFPDraft.section_order.asc()).all()
                current_total_words = sum(count_words(d.draft_content) for d in drafts)
                remaining_budget = max_words_total - current_total_words
                
                if remaining_budget < 100:
                    print(f"[generation_service] Budget nearly exhausted ({remaining_budget} left). Forcing concise generation.")

                # Skip if already generated
                existing = db.query(RFPDraft).filter(
                    RFPDraft.rfp_id == rfp.id, RFPDraft.version == version,
                    RFPDraft.section_name == section["name"]
                ).first()
                if existing:
                    completed += 1
                    continue

                # PART 5: Update heartbeat so stuck-job detector knows we're alive
                if job:
                    update_job_heartbeat(
                        db, job.id,
                        step=f"Generating: {section['name']} ({completed+1}/{total})",
                        progress=int((completed / total) * 90)
                    )

                # Generate with retry
                try:
                    for attempt in range(3):
                        result = generate_section(
                            db=db, rfp=rfp,
                            section_name=section["name"], section_order=section["order"],
                            version=version, rfp_intel=rfp_intel,
                            length_mode=length_mode, remaining_budget=remaining_budget
                        )
                        if result: break
                        time.sleep(10 * (attempt + 1))
                except QuotaExhaustedError as qe:
                    rfp.current_status = "generation_paused"
                    rfp.status_message = "Paused due to AI provider quota. You can resume later from the dashboard."
                    db.commit()
                    if job:
                        fail_job(db, job.id, str(qe), "Generation paused due to AI quota. Resume when available.", retryable=True)
                    return
                except Exception as e:
                    print(f"Error generating section '{section['name']}': {e}")

                completed += 1
                print(f"[generation_service] [{completed}/{total}] '{section['name']}' done")
                time.sleep(2)

        # Finalize and Compress — BUG 4 FIX: use get_ordered_drafts() for deterministic order
        db.refresh(rfp)
        final_drafts = get_ordered_drafts(db, rfp_id, version)
        final_word_count = sum(count_words(d.draft_content) for d in final_drafts)
        est_pages = int(final_word_count / 275) # Est 275 words per page

        print(f"[generation_service] Generated Word Count: {final_word_count}")
        print(f"[generation_service] Estimated Page Count: {est_pages}")

        if final_word_count > max_words_total:
            rfp.status_message = "Compressing proposal to fit length limits..."
            db.commit()
            compress_draft_if_needed(db, rfp_id, version, max_words_total)

            # Recalculate after compression — always use ordered query
            final_drafts = get_ordered_drafts(db, rfp_id, version)
            final_word_count = sum(count_words(d.draft_content) for d in final_drafts)
            est_pages = int(final_word_count / 275)
            print(f"[generation_service] Compressed Word Count: {final_word_count}")

        rfp.current_status = "ai_draft_ready"
        rfp.status_message = f"AI Draft Ready ({length_mode}). ~{est_pages} pages, {final_word_count} words."
        db.commit()

        # PART 5: Mark job as completed
        if job:
            complete_job(db, job.id, f"Draft complete. {total} sections, ~{est_pages} pages, {final_word_count} words.")

        # Quality check
        try:
            from app.services.quality_service import run_quality_check
            run_quality_check(db, rfp_id)
        except Exception as qe:
            print(f"[generation_service] Quality check failed: {qe}")

        from app.services.notification_service import create_notification
        try:
            from app.models.rfp import RFPAssignment
            from app.models.user import User
            assignment = db.query(RFPAssignment).filter(
                RFPAssignment.rfp_id == rfp_id,
                RFPAssignment.assignment_status == "active"
            ).first()
            if assignment:
                sa_msg = f"AI draft is ready for your review — '{rfp.title}' ({length_mode} mode, ~{est_pages} pages)."
                sa_n = create_notification(db, user_id=assignment.assigned_to, message=sa_msg, rfp_id=rfp_id, type="success")
                sa_user = db.query(User).filter(User.id == assignment.assigned_to).first()
                print(f"[notification] Draft-ready SA: id={sa_n.id if sa_n else None} rfp_id={rfp_id} user_id={assignment.assigned_to} role={sa_user.role if sa_user else 'SA'} is_read=False")
                pm_msg = f"AI draft generated for '{rfp.title}' ({length_mode}, ~{est_pages} pages)."
                pm_n = create_notification(db, user_id=assignment.assigned_by, message=pm_msg, rfp_id=rfp_id, type="info")
                print(f"[notification] Draft-ready PM: id={pm_n.id if pm_n else None} rfp_id={rfp_id} user_id={assignment.assigned_by} is_read=False")
            else:
                fb_msg = f"AI draft ready ({length_mode} mode). ~{est_pages} pages generated for '{rfp.title}'."
                fb_n = create_notification(db, user_id=rfp.uploaded_by, message=fb_msg, rfp_id=rfp_id, type="success")
                print(f"[notification] Draft-ready fallback uploader: id={fb_n.id if fb_n else None} rfp_id={rfp_id} user_id={rfp.uploaded_by}")
        except Exception as notif_err:
            print(f"[generation_service] Draft-ready notification failed (non-fatal): {notif_err}")

    except Exception as e:
        print(f"[generation_service] Fatal error: {e}")
        try:
            rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
            if rfp:
                # PART 5: Use paused instead of error so user can resume
                rfp.current_status = "generation_paused"
                rfp.status_message = "Generation encountered an error. You can retry from the dashboard."
                db.commit()
            if job:
                fail_job(db, job.id,
                    internal_error=str(e)[:2000],
                    user_message="Generation failed. You can retry from the dashboard.",
                    retryable=True
                )
        except Exception as inner:
            print(f"[generation_service] Error during error-handling: {inner}")
    finally:
        db.close()


def generate_full_proposal(db: Session, rfp_id: int, mode: str = "standard"):
    """
    Alias for confirm-generation endpoint — runs in the calling thread's DB session context.
    For background use, call run_generation_job() in a separate thread with its own session.
    """
    import threading
    t = threading.Thread(
        target=run_generation_job,
        kwargs={"rfp_id": rfp_id, "length_mode": mode},
        daemon=True
    )
    t.start()
