"""
job_service.py
==============
PART 5: Job State Management and Stuck Job Recovery.

Replaces manual DB status resets with intelligent automated recovery.
- detect_and_repair_stuck_jobs(): Background health check, finds stalled jobs
- repair_rfp_status(): Infers correct status from DB evidence
- create_job(), update_job_heartbeat(), complete_job(), fail_job()
"""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.rfp import RFPDocument, BackgroundJob, AuditLog, RFPDraft, GeneratedDocument

# Jobs running longer than this threshold without a heartbeat are considered stuck
STUCK_THRESHOLD_MINUTES = 10
ANALYSIS_TIMEOUT_MINUTES = 10
GENERATION_TIMEOUT_MINUTES = 60

# Statuses that indicate a job is actively being worked on
ACTIVE_STATUSES = {"queued_for_processing", "processing_summary", "analyzing_structure",
                   "extracting_metrics", "finalizing_insights", "generating_draft", "in_drafting"}


def create_job(db: Session, rfp_id: int, job_type: str, total_steps: int = 5, job_subtype: str = None) -> BackgroundJob:
    """Create a new tracked background job."""
    # Prevent duplicate active jobs of same type
    existing = db.query(BackgroundJob).filter(
        BackgroundJob.rfp_id == rfp_id,
        BackgroundJob.job_type == job_type,
        BackgroundJob.status.in_(["queued", "running"])
    ).first()
    if existing:
        print(f"[job_service] Duplicate job prevented: {job_type} for RFP {rfp_id}")
        return existing

    job = BackgroundJob(
        rfp_id=rfp_id,
        job_type=job_type,
        job_subtype=job_subtype,
        status="queued",
        progress_percentage=0,
        total_steps=total_steps,
        last_heartbeat=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def update_job_heartbeat(db: Session, job_id: int, step: str = None, progress: int = None):
    """Called periodically by a running job to signal it's alive."""
    job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
    if job:
        job.last_heartbeat = datetime.utcnow()
        job.status = "running"
        if step:
            job.current_step = step
        if progress is not None:
            job.progress_percentage = min(progress, 99)
        db.commit()


def complete_job(db: Session, job_id: int, message: str = "Completed successfully"):
    """Mark a job as successfully completed."""
    job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
    if job:
        job.status = "completed"
        job.progress_percentage = 100
        job.completed_at = datetime.utcnow()
        job.user_message = message
        db.commit()


def fail_job(db: Session, job_id: int, internal_error: str, user_message: str, retryable: bool = True):
    """Mark a job as failed with safe and internal messages."""
    job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
    if job:
        job.status = "failed_retryable" if retryable else "failed_final"
        job.failed_at = datetime.utcnow()
        job.internal_error = internal_error[:2000]  # Truncate for DB
        job.user_message = user_message
        job.retry_count = (job.retry_count or 0) + 1
        db.commit()


def get_job_progress(db: Session, rfp_id: int, job_type: str) -> dict:
    """Get the latest progress for a job type on an RFP."""
    job = db.query(BackgroundJob).filter(
        BackgroundJob.rfp_id == rfp_id,
        BackgroundJob.job_type == job_type,
    ).order_by(BackgroundJob.started_at.desc()).first()

    if not job:
        return {"status": "not_started", "progress_percentage": 0, "current_step": None, "user_message": None}

    return {
        "job_id": job.id,
        "status": job.status,
        "progress_percentage": job.progress_percentage,
        "current_step": job.current_step,
        "user_message": job.user_message,
        "retry_count": job.retry_count,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def detect_and_repair_stuck_jobs(db: Session) -> list[dict]:
    """
    PART 5: Scan for stuck jobs and repair them.
    Called by a background health check or triggered by the repair endpoint.
    
    A job is stuck if:
    - status == 'running'
    - last_heartbeat is older than threshold
    """
    now = datetime.utcnow()
    threshold = now - timedelta(minutes=STUCK_THRESHOLD_MINUTES)
    repaired = []

    stuck_jobs = db.query(BackgroundJob).filter(
        BackgroundJob.status == "running",
        BackgroundJob.last_heartbeat < threshold
    ).all()

    for job in stuck_jobs:
        old_status = job.status
        job.status = "failed_retryable"
        job.failed_at = now
        job.user_message = "Job stalled without completing. You can retry from the dashboard."
        job.internal_error = f"Stuck detected at {now} — last heartbeat was {job.last_heartbeat}"
        db.commit()

        # Also fix the RFP status
        rfp_repair = repair_rfp_status(job.rfp_id, db, commit=False)
        db.commit()

        repaired.append({
            "job_id": job.id,
            "rfp_id": job.rfp_id,
            "job_type": job.job_type,
            "old_status": old_status,
            "new_status": job.status,
            "rfp_new_status": rfp_repair.get("new_status"),
        })
        print(f"[job_service] Repaired stuck job {job.id} for RFP {job.rfp_id}")

    # Also repair RFPs stuck in processing statuses with no running job
    orphaned_rfps = db.query(RFPDocument).filter(
        RFPDocument.current_status.in_(list(ACTIVE_STATUSES) + ["rate_limit_error"])
    ).all()

    for rfp in orphaned_rfps:
        # Check if a running job exists
        active_job = db.query(BackgroundJob).filter(
            BackgroundJob.rfp_id == rfp.id,
            BackgroundJob.status.in_(["queued", "running"])
        ).first()
        if not active_job:
            # RFP is in an active state but no job is running — orphaned
            rfp_repair = repair_rfp_status(rfp.id, db, commit=True)
            repaired.append({
                "rfp_id": rfp.id,
                "type": "orphaned_rfp",
                "old_status": rfp.current_status,
                "new_status": rfp_repair.get("new_status"),
            })

    return repaired


def repair_rfp_status(rfp_id: int, db: Session, commit: bool = True) -> dict:
    """
    Intelligent status repair based on DB evidence.
    
    Logic:
    - Has summary_json AND current_status in analyzing states → ready_for_pm_review
    - Has draft sections AND generated doc → ai_draft_ready
    - Has assignment → assigned_to_sa
    - rate_limit_error → paused (with friendly message)
    - Otherwise → uploaded (safe fallback)
    """
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp:
        return {"error": "RFP not found"}

    old_status = rfp.current_status
    new_status = old_status

    # Evidence-based status inference
    has_summary = bool(rfp.summary_json)
    has_drafts = db.query(RFPDraft).filter(RFPDraft.rfp_id == rfp_id).count() > 0
    has_doc = db.query(GeneratedDocument).filter(
        GeneratedDocument.rfp_id == rfp_id,
        GeneratedDocument.is_available == True
    ).first()
    is_analyzing = old_status in ACTIVE_STATUSES or old_status == "rate_limit_error"

    if old_status == "rate_limit_error":
        new_status = "paused"
        rfp.status_message = "Paused due to AI provider quota. You can retry when quota is available."
    elif is_analyzing and has_doc:
        new_status = "ai_draft_ready"
    elif is_analyzing and has_drafts:
        new_status = "ai_draft_ready"
    elif is_analyzing and has_summary:
        new_status = "pending-review"
    elif is_analyzing and not has_summary:
        new_status = "uploaded"
    
    if new_status != old_status:
        rfp.current_status = new_status
        db.add(AuditLog(
            rfp_id=rfp_id,
            action="auto_status_repair",
            old_value=old_status,
            new_value=new_status,
        ))
        if commit:
            db.commit()

    return {"rfp_id": rfp_id, "old_status": old_status, "new_status": new_status}


def get_generation_confirmation_data(rfp_id: int, architect_user, mode: str, db: Session) -> dict:
    """
    PART 3: Build the data shown in the human approval modal before generation starts.
    """
    from app.services.context_service import load_rfp_context
    ctx = load_rfp_context(rfp_id, db)

    mode_pages = {"short": "10–20", "standard": "20–35", "comprehensive": "35–60"}
    mode_time = {"short": "15–25 min", "standard": "25–45 min", "comprehensive": "45–90 min"}
    mode_provider = "Gemini (deep reasoning)"

    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    draft_count = db.query(RFPDraft).filter(RFPDraft.rfp_id == rfp_id).count()

    return {
        "rfp_id": rfp_id,
        "rfp_title": rfp.title if rfp else "Unknown",
        "client_name": ctx.get("client_name"),
        "architect_name": f"{architect_user.full_name}" if hasattr(architect_user, 'full_name') else str(architect_user),
        "proposal_mode": mode,
        "estimated_pages": mode_pages.get(mode, "20–35"),
        "estimated_time": mode_time.get(mode, "25–45 min"),
        "estimated_provider": mode_provider,
        "existing_sections": draft_count,
        "will_overwrite": draft_count > 0,
        "warning": "This will overwrite existing generated sections." if draft_count > 0 else None,
    }
