"""
rfp_tools.py
============
PART 6: LangGraph / MCP Readiness.

Internal tool functions with typed signatures.
These are kept as Python functions now, but structured to be directly
wrappable as MCP tools or LangGraph nodes later.

Usage pattern:
    from app.tools.rfp_tools import get_rfp_intelligence
    result = get_rfp_intelligence(rfp_id=42, db=db)

Future MCP wrapping (no code changes needed, just expose with MCP server):
    @mcp_tool("get_rfp_intelligence")
    async def get_rfp_intelligence_mcp(rfp_id: int) -> dict:
        db = next(get_db())
        return get_rfp_intelligence(rfp_id, db)
"""
from typing import Optional
from sqlalchemy.orm import Session


# ── READ TOOLS (Safe for LLM-initiated calls) ─────────────────────────────────

def get_rfp_metadata(rfp_id: int, db: Session) -> dict:
    """Return lightweight metadata about an RFP (title, client, deadline, status)."""
    from app.models.rfp import RFPDocument, RFPMetadata
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp:
        return {"error": f"RFP {rfp_id} not found"}
    meta = db.query(RFPMetadata).filter(RFPMetadata.rfp_id == rfp_id).first()
    return {
        "rfp_id": rfp_id,
        "title": rfp.title,
        "client_name": rfp.client_name,
        "status": rfp.current_status,
        "lifecycle_status": rfp.lifecycle_status,
        "generation_mode": rfp.proposal_length_mode or rfp.generation_mode,
        "deadline": meta.deadline.isoformat() if meta and meta.deadline else None,
        "estimated_value": str(meta.estimated_value) if meta and meta.estimated_value else None,
    }


def get_rfp_intelligence(rfp_id: int, db: Session) -> dict:
    """Return all stored RFP intelligence from PostgreSQL (no AI call)."""
    from app.services.context_service import load_rfp_context
    return load_rfp_context(rfp_id, db)


def get_rfp_file_path(rfp_id: int, db: Session) -> dict:
    """Return the local file path for the original RFP document."""
    import os
    from app.models.rfp import RFPDocument
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp:
        return {"error": "RFP not found"}
    return {
        "rfp_id": rfp_id,
        "file_path": rfp.file_path,
        "file_name": rfp.file_name,
        "file_type": rfp.file_type,
        "file_exists": os.path.exists(rfp.file_path or ""),
    }


def get_generated_sections(rfp_id: int, db: Session) -> dict:
    """Return all generated draft sections with evaluator status."""
    from app.models.rfp import RFPDraft
    drafts = db.query(RFPDraft).filter(RFPDraft.rfp_id == rfp_id).order_by(RFPDraft.section_order).all()
    return {
        "rfp_id": rfp_id,
        "total_sections": len(drafts),
        "sections": [
            {
                "id": d.id,
                "section_name": d.section_name,
                "section_order": d.section_order,
                "word_count": d.word_count,
                "evaluation_status": d.evaluation_status,
                "evaluator_score": d.evaluator_score,
                "attempt_count": d.attempt_count,
                "is_final": d.is_final,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in drafts
        ],
    }


def get_chat_history(rfp_id: int, db: Session, limit: int = 20) -> dict:
    """Return recent chat history for an RFP."""
    from app.models.rfp import ChatHistory
    chats = db.query(ChatHistory).filter(
        ChatHistory.rfp_id == rfp_id
    ).order_by(ChatHistory.created_at.desc()).limit(limit).all()
    return {
        "rfp_id": rfp_id,
        "chat_count": len(chats),
        "history": [
            {
                "role": c.role,
                "message": c.message[:200],
                "provider_used": c.provider_used,
                "tokens_used": c.tokens_used,
                "handled_locally": c.handled_locally,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in reversed(chats)
        ],
    }


# ── WRITE TOOLS (Require human approval before LLM can trigger) ───────────────

def start_analysis_job(rfp_id: int, db: Session, triggered_by: int = None) -> dict:
    """
    Start a background analysis job.
    HUMAN APPROVAL REQUIRED before calling from LLM context.
    """
    from app.services.job_service import create_job
    from app.models.rfp import RFPDocument, AuditLog

    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp:
        return {"error": "RFP not found"}

    job = create_job(db, rfp_id, "analysis", total_steps=5)
    rfp.current_status = "queued_for_processing"
    db.add(AuditLog(rfp_id=rfp_id, user_id=triggered_by, action="analysis_job_started", new_value=str(job.id)))
    db.commit()
    return {"job_id": job.id, "status": "queued", "rfp_id": rfp_id}


def start_generation_job(rfp_id: int, mode: str, db: Session, confirmed: bool = False, triggered_by: int = None) -> dict:
    """
    Start a draft generation job.
    HUMAN APPROVAL REQUIRED: confirmed=True must be explicitly set by the PM/SA.
    """
    if not confirmed:
        return {"error": "Human confirmation required. Set confirmed=True after user approves generation."}

    from app.services.job_service import create_job
    from app.models.rfp import RFPDocument, AuditLog

    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp:
        return {"error": "RFP not found"}

    job = create_job(db, rfp_id, "generation", total_steps=10)
    rfp.current_status = "generating_draft"
    rfp.proposal_length_mode = mode
    db.add(AuditLog(rfp_id=rfp_id, user_id=triggered_by, action="generation_job_started", new_value=f"mode={mode}"))
    db.commit()
    return {"job_id": job.id, "status": "queued", "rfp_id": rfp_id, "mode": mode}


def run_quality_check(rfp_id: int, db: Session) -> dict:
    """Run the post-generation quality check."""
    try:
        from app.services.quality_service import run_quality_check as _run_qc
        return _run_qc(db, rfp_id)
    except Exception as e:
        return {"error": str(e), "rfp_id": rfp_id}


def export_docx(rfp_id: int, db: Session) -> dict:
    """Export the generated proposal to DOCX."""
    try:
        from app.services.export_service import export_to_docx
        return export_to_docx(db, rfp_id)
    except Exception as e:
        return {"error": str(e), "rfp_id": rfp_id}


def submit_for_pm_review(rfp_id: int, sa_user_id: int, db: Session) -> dict:
    """SA submits the draft for PM review (with confirmation guard)."""
    from app.models.rfp import RFPDocument, AuditLog
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp:
        return {"error": "RFP not found"}
    if rfp.current_status not in ["ai_draft_ready", "under_sa_review"]:
        return {"error": f"Cannot submit from status '{rfp.current_status}'. Draft must be ready."}

    rfp.current_status = "submitted_for_review"
    rfp.submitted_at = __import__("datetime").datetime.utcnow()
    rfp.submitted_by = sa_user_id
    db.add(AuditLog(rfp_id=rfp_id, user_id=sa_user_id, action="submitted_for_pm_review"))
    db.commit()
    return {"success": True, "new_status": "submitted_for_review"}


# ── Future LangGraph Node Mapping ─────────────────────────────────────────────
# 
# When migrating to LangGraph, each tool maps to a node:
#
# UploadNode        → saves file, creates RFP record
# ExtractMetadataNode → get_rfp_metadata() after analysis
# PMDecisionNode    → human approval gate
# HumanApprovalNode → confirm-generation endpoint
# AssignArchitectNode → assignment with duplicate guard
# DraftGenerationNode → start_generation_job(confirmed=True)
# EvaluatorNode     → evaluator_optimizer_loop()
# QualityCheckNode  → run_quality_check()
# SAReviewNode      → get_generated_sections(), submit_for_pm_review()
# PMFinalApprovalNode → final-approval endpoint
#
# State persistence → use PostgreSQL as checkpointer (not LLM context)
