"""
context_service.py
==================
PART 1: Persistent Context for 2-3 weeks.

Manages all durable RFP intelligence stored in PostgreSQL.
- load_rfp_context: Returns all DB-stored intelligence WITHOUT calling any LLM.
- ensure_gemini_file_available: Re-uploads original file to Gemini if URI expired.
- extract_and_store_intelligence: Populates dedicated JSON fields after analysis.

When a PM returns after 2-3 weeks, load_rfp_context provides everything they need.
Gemini is only re-invoked if the user explicitly requests deep document reasoning.
"""
import os
import json
import time
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.rfp import RFPDocument, RFPMetadata, RFPDraft, GeneratedDocument, AuditLog
from app.core.config import settings

# Gemini file URI expires after ~48 hours (actual TTL depends on Google policy)
GEMINI_FILE_TTL_HOURS = 47  # Re-upload 1 hour before expiry for safety


def load_rfp_context(rfp_id: int, db: Session) -> dict:
    """
    Load complete RFP context from PostgreSQL only.
    No LLM call. Safe to call at any time.
    Returns a dict suitable for AI task routing and chat context.
    """
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp:
        return {}

    metadata = db.query(RFPMetadata).filter(RFPMetadata.rfp_id == rfp_id).first()
    drafts = db.query(RFPDraft).filter(RFPDraft.rfp_id == rfp_id).all()
    docs = db.query(GeneratedDocument).filter(GeneratedDocument.rfp_id == rfp_id).all()

    # Parse intelligence JSON fields safely
    def _safe_json(raw):
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    summary = _safe_json(rfp.summary_json)

    context = {
        # Identity
        "rfp_id": rfp_id,
        "title": rfp.title,
        "client_name": rfp.client_name,
        "current_status": rfp.current_status,
        "lifecycle_status": rfp.lifecycle_status,
        "generation_mode": rfp.proposal_length_mode or rfp.generation_mode or "standard",
        # Metadata
        "deadline": metadata.deadline.strftime("%Y-%m-%d") if metadata and metadata.deadline else None,
        "budget": str(metadata.budget) if metadata and metadata.budget else None,
        "currency": metadata.currency if metadata else "USD",
        "estimated_value": str(metadata.estimated_value) if metadata and metadata.estimated_value else None,
        # Intelligence — dedicated fields first, then summary_json fallback
        "summary": summary,
        "risks": _safe_json(rfp.risks_json) or (summary.get("risks") if summary else None),
        "compliance": _safe_json(rfp.compliance_json) or (summary.get("compliance_summary") if summary else None),
        "commercial_terms": _safe_json(rfp.commercial_json) or (summary.get("commercial_terms") if summary else None),
        "requirements": _safe_json(rfp.requirements_json) or (summary.get("key_requirements") if summary else None),
        "executive_summary": summary.get("executive_summary") if summary else None,
        "recommended_action": summary.get("recommended_action") if summary else None,
        "effort_estimate": summary.get("effort_estimate") if summary else None,
        # File info
        "has_original_file": bool(rfp.file_path and os.path.exists(rfp.file_path or "")),
        "gemini_uri_valid": _is_gemini_uri_valid(rfp),
        "file_type": rfp.file_type,
        "file_size_kb": rfp.file_size_kb,
        # Draft status
        "draft_count": len(drafts),
        "evaluation_summary": _build_evaluation_summary(drafts),
        "has_generated_doc": any(d.is_available for d in docs),
    }
    return context


def _is_gemini_uri_valid(rfp: RFPDocument) -> bool:
    """Returns True if Gemini file URI exists and is not expired."""
    if not rfp.gemini_file_uri:
        return False
    if rfp.gemini_file_expires_at and datetime.utcnow() >= rfp.gemini_file_expires_at:
        return False
    return True


def _build_evaluation_summary(drafts) -> dict:
    """Summarize evaluator status across all draft sections."""
    total = len(drafts)
    if total == 0:
        return {"total": 0}
    passed = sum(1 for d in drafts if d.evaluation_status == "passed")
    failed = sum(1 for d in drafts if d.evaluation_status == "failed")
    needs_review = sum(1 for d in drafts if d.evaluation_status == "needs_human_review")
    pending = total - passed - failed - needs_review
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "needs_human_review": needs_review,
        "pending": pending,
        "completion_pct": round((passed / total) * 100) if total > 0 else 0,
    }


def ensure_gemini_file_available(rfp_id: int, db: Session) -> str | None:
    """
    PART 1: Gemini URI expiry management.
    
    Checks if the Gemini file URI is still valid. If expired or missing,
    re-uploads the original file from local storage and updates the DB.
    
    Returns: Valid Gemini file name/URI, or None if file not available.
    """
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp:
        return None

    # Check if URI is still valid
    if _is_gemini_uri_valid(rfp):
        # Verify with Gemini API (quick check)
        try:
            from google import genai
            g_client = genai.Client(api_key=settings.GEMINI_API_KEY)
            g_client.files.get(name=rfp.gemini_file_uri)
            return rfp.gemini_file_uri
        except Exception:
            print(f"[context_service] Gemini URI check failed for RFP {rfp_id}, will re-upload.")

    # URI expired or invalid — re-upload from local storage
    if not rfp.file_path or not os.path.exists(rfp.file_path):
        print(f"[context_service] Original file not found locally for RFP {rfp_id}. Cannot re-upload.")
        return None

    try:
        from google import genai
        g_client = genai.Client(api_key=settings.GEMINI_API_KEY)
        
        print(f"[context_service] Re-uploading RFP {rfp_id} file to Gemini: {rfp.file_path}")
        file_ref = g_client.files.upload(
            file=rfp.file_path,
            config={"display_name": rfp.file_name or f"rfp_{rfp_id}"}
        )

        # Wait for ACTIVE state (up to 60s)
        for _ in range(12):
            file_ref = g_client.files.get(name=file_ref.name)
            if file_ref.state.name == "ACTIVE":
                break
            time.sleep(5)

        if file_ref.state.name != "ACTIVE":
            print(f"[context_service] File upload stalled for RFP {rfp_id}")
            return None

        # Update DB with new URI and expiry
        now = datetime.utcnow()
        rfp.gemini_file_uri = file_ref.name
        rfp.gemini_file_uploaded_at = now
        rfp.gemini_file_expires_at = now + timedelta(hours=GEMINI_FILE_TTL_HOURS)
        db.add(AuditLog(
            rfp_id=rfp_id,
            action="gemini_file_reuploaded",
            new_value=file_ref.name
        ))
        db.commit()
        print(f"[context_service] Gemini file re-uploaded for RFP {rfp_id}: {file_ref.name}")
        return file_ref.name

    except Exception as e:
        print(f"[context_service] Gemini re-upload failed for RFP {rfp_id}: {e}")
        return None


def extract_and_store_intelligence(rfp_id: int, summary_data: dict, db: Session):
    """
    After AI analysis, split the monolithic summary_json into dedicated fields
    for faster retrieval and context persistence.
    """
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp:
        return

    if summary_data.get("risks"):
        rfp.risks_json = json.dumps(summary_data["risks"])
    if summary_data.get("compliance_summary"):
        rfp.compliance_json = json.dumps(summary_data["compliance_summary"])
    if summary_data.get("commercial_terms"):
        rfp.commercial_json = json.dumps(summary_data["commercial_terms"])
    if summary_data.get("key_requirements"):
        rfp.requirements_json = json.dumps(summary_data["key_requirements"])

    db.commit()
    print(f"[context_service] Intelligence stored for RFP {rfp_id}")
