from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Numeric, Boolean, Date, ARRAY
from sqlalchemy.sql import func
from app.core.database import Base

class RFPDocument(Base):
    __tablename__ = "rfp_documents"
    id             = Column(Integer, primary_key=True, index=True)
    title          = Column(String(300), nullable=False)
    client_name    = Column(String(200))
    uploaded_by    = Column(Integer, ForeignKey("users.id"))
    file_path      = Column(Text)
    file_name      = Column(String(255))
    file_type      = Column(String(20))
    file_size_kb   = Column(Integer)
    current_status = Column(String(50), default="uploaded")
    status_message = Column(Text, nullable=True)
    gemini_file_uri= Column(String(500), nullable=True)
    gemini_cache_id = Column(String(500), nullable=True) # ID from Gemini Context Caching
    cache_expiry    = Column(DateTime, nullable=True)    # TTL management
    full_text       = Column(Text, nullable=True)        # Extracted text for re-hydration
    summary_json   = Column(Text, nullable=True)
    submitted_at   = Column(DateTime, nullable=True)        # When SA submitted for PM review
    submitted_by   = Column(Integer, ForeignKey("users.id"), nullable=True)  # Which SA submitted
    quality_status = Column(Text, nullable=True)            # JSON: quality check results
    generation_mode = Column(String(20), default="short")
    document_quality = Column(String(50), nullable=True)     # insufficient_rfp_detail, sufficient, valid_rfp, extraction_failed_or_scanned_pdf
    word_count       = Column(Integer, nullable=True)
    page_count       = Column(Integer, nullable=True)
    extracted_text_length = Column(Integer, nullable=True)
    richness_reason  = Column(Text, nullable=True)
    created_at     = Column(DateTime, default=func.now())
    updated_at     = Column(DateTime, default=func.now(), onupdate=func.now())
    # ── PART 1: Persistent Context (2-3 weeks) ───────────────────────────────
    gemini_file_uploaded_at  = Column(DateTime, nullable=True)    # Track upload time
    gemini_file_expires_at   = Column(DateTime, nullable=True)    # 48hr TTL from upload
    requirements_json        = Column(Text, nullable=True)         # Extracted requirements
    risks_json               = Column(Text, nullable=True)         # Extracted risks
    compliance_json          = Column(Text, nullable=True)         # Compliance summary
    commercial_json          = Column(Text, nullable=True)         # Commercial terms
    lifecycle_status         = Column(String(50), nullable=True)   # Coarse lifecycle for PM
    proposal_length_mode     = Column(String(20), default="standard")  # short/standard/comprehensive
    # ─────────────────────────────────────────────────────────────────────────

class RFPMetadata(Base):
    __tablename__ = "rfp_metadata"
    id              = Column(Integer, primary_key=True, index=True)
    rfp_id          = Column(Integer, ForeignKey("rfp_documents.id"), unique=True)
    deadline        = Column(Date)
    budget          = Column(Numeric(18, 2))
    currency        = Column(String(10), default="USD")
    department      = Column(String(150))
    estimated_value = Column(Numeric(18, 2))
    priority        = Column(String(20), default="medium")
    complexity_score = Column(Integer)
    created_at      = Column(DateTime, default=func.now())
    updated_at      = Column(DateTime, default=func.now(), onupdate=func.now())

class RFPAssignment(Base):
    __tablename__ = "rfp_assignments"
    id                = Column(Integer, primary_key=True, index=True)
    rfp_id            = Column(Integer, ForeignKey("rfp_documents.id"))
    assigned_to       = Column(Integer, ForeignKey("users.id"))
    assigned_by       = Column(Integer, ForeignKey("users.id"))
    assignment_status = Column(String(30), default="active")
    notes             = Column(Text)
    assigned_at       = Column(DateTime, default=func.now())
    updated_at        = Column(DateTime, default=func.now(), onupdate=func.now())

class RFPApproval(Base):
    __tablename__ = "rfp_approvals"
    id          = Column(Integer, primary_key=True, index=True)
    rfp_id      = Column(Integer, ForeignKey("rfp_documents.id"))
    approved_by = Column(Integer, ForeignKey("users.id"))
    decision    = Column(String(20), nullable=False)
    reason      = Column(Text)
    decided_at  = Column(DateTime, default=func.now())

class RFPComment(Base):
    __tablename__ = "rfp_comments"
    id           = Column(Integer, primary_key=True, index=True)
    rfp_id       = Column(Integer, ForeignKey("rfp_documents.id"))
    user_id      = Column(Integer, ForeignKey("users.id"))
    entity_type  = Column(String(50))
    entity_id    = Column(Integer)
    comment_text = Column(Text, nullable=False)
    created_at   = Column(DateTime, default=func.now())
    updated_at   = Column(DateTime, default=func.now(), onupdate=func.now())

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id          = Column(Integer, primary_key=True, index=True)
    rfp_id      = Column(Integer, ForeignKey("rfp_documents.id"))
    user_id     = Column(Integer, ForeignKey("users.id"))
    action      = Column(String(100), nullable=False)
    entity_type = Column(String(50))
    entity_id   = Column(Integer)
    old_value   = Column(Text)
    new_value   = Column(Text)
    ip_address  = Column(String(45))
    created_at  = Column(DateTime, default=func.now())

class RFPDraft(Base):
    __tablename__ = "rfp_drafts"
    id            = Column(Integer, primary_key=True, index=True)
    rfp_id        = Column(Integer, ForeignKey("rfp_documents.id"))
    section_name  = Column(String(200), nullable=True) # e.g., "Executive Summary"
    section_order = Column(Integer, default=1)
    version       = Column(Integer, default=1)
    draft_content = Column(Text, nullable=False)
    created_by    = Column(Integer, ForeignKey("users.id"))
    is_final      = Column(Boolean, default=False)
    created_at    = Column(DateTime, default=func.now())
    # ── PART 4: Evaluator-Optimizer Loop ─────────────────────────────────────
    evaluation_status  = Column(String(30), default="pending")  # pending/passed/failed/needs_human_review
    evaluator_score    = Column(Integer, nullable=True)          # 0-100
    evaluator_feedback = Column(Text, nullable=True)             # Issues found
    attempt_count      = Column(Integer, default=1)              # Generation attempts
    word_count         = Column(Integer, nullable=True)          # For budget check
    # ─────────────────────────────────────────────────────────────────────────

class RFPRequirement(Base):
    __tablename__ = "rfp_requirements"
    id                = Column(Integer, primary_key=True, index=True)
    rfp_id            = Column(Integer, ForeignKey("rfp_documents.id"))
    requirement_text  = Column(Text, nullable=False)
    status            = Column(String(50), default="pending") # compliant, partial, non-compliant, pending
    response_strategy = Column(Text)
    notes             = Column(Text)
    category          = Column(String(100)) # technical, mandatory, eligibility, etc.
    created_at        = Column(DateTime, default=func.now())
    updated_at        = Column(DateTime, default=func.now(), onupdate=func.now())

class GeneratedDocument(Base):
    __tablename__ = "generated_documents"
    id            = Column(Integer, primary_key=True, index=True)
    rfp_id        = Column(Integer, ForeignKey("rfp_documents.id"))
    file_name     = Column(String(255))
    file_path     = Column(Text)
    download_url  = Column(Text, nullable=True)
    document_type = Column(String(50), default="PROPOSAL_DRAFT")
    version       = Column(Integer, default=1)
    status        = Column(String(50), default="ready")
    is_available  = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=func.now())

class BackgroundJob(Base):
    __tablename__ = "background_jobs"
    id                  = Column(Integer, primary_key=True, index=True)
    job_type            = Column(String(50), nullable=False) # 'analysis', 'generation', 'export'
    rfp_id              = Column(Integer, ForeignKey("rfp_documents.id"))
    status              = Column(String(50), default="queued") # 'queued', 'running', 'completed', 'failed', 'paused'
    progress_percentage = Column(Integer, default=0)
    current_step        = Column(String(200))
    total_steps         = Column(Integer, default=0)
    started_at          = Column(DateTime, default=func.now())
    completed_at        = Column(DateTime, nullable=True)
    failed_at           = Column(DateTime, nullable=True)
    internal_error      = Column(Text, nullable=True)       # Never exposed to frontend
    user_message        = Column(Text, nullable=True)       # Safe message for UI
    # ── PART 5: Stuck Job Recovery ───────────────────────────────────────────
    retry_count         = Column(Integer, default=0)        # Number of retry attempts
    last_heartbeat      = Column(DateTime, nullable=True)   # Updated by running job
    job_subtype         = Column(String(50), nullable=True) # e.g., 'section_generation'
    # ─────────────────────────────────────────────────────────────────────────

class ChatHistory(Base):
    __tablename__ = "chat_history"
    id                  = Column(Integer, primary_key=True, index=True)
    rfp_id              = Column(Integer, ForeignKey("rfp_documents.id"))
    user_id             = Column(Integer, ForeignKey("users.id"))
    role                = Column(String(20), nullable=False) # 'user', 'ai'
    message             = Column(Text, nullable=False)
    response            = Column(Text, nullable=True)
    source_context_used = Column(String(50), nullable=True) # 'db', 'gemini_file', 'generated_draft', 'local'
    handled_locally     = Column(Boolean, default=False)
    tokens_used         = Column(Integer, default=0)
    provider_used       = Column(String(50), nullable=True)
    model_used          = Column(String(100), nullable=True)  # Track exact model used
    created_at          = Column(DateTime, default=func.now())
