from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.models.rfp import RFPDraft, RFPDocument, AuditLog

def save_draft(db: Session, rfp_id: int, user_id: int, draft_content: str, is_final: bool = False):
    # Determine the next version
    latest_draft = db.query(RFPDraft).filter(RFPDraft.rfp_id == rfp_id).order_by(desc(RFPDraft.version)).first()
    next_version = (latest_draft.version + 1) if latest_draft else 1

    draft = RFPDraft(
        rfp_id=rfp_id,
        version=next_version,
        draft_content=draft_content,
        created_by=user_id,
        is_final=is_final
    )
    db.add(draft)
    
    # Update RFP status if draft is marked as final
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if rfp and is_final:
        rfp.current_status = "under_review"
    elif rfp and rfp.current_status == "assigned_to_sa":
        rfp.current_status = "in_drafting"
        
    action_type = "draft_finalized" if is_final else "draft_saved"
    log = AuditLog(
        rfp_id=rfp_id,
        user_id=user_id,
        action=action_type,
        new_value=f"Version {next_version}"
    )
    db.add(log)
    db.commit()
    db.refresh(draft)
    return draft

def get_latest_draft(db: Session, rfp_id: int):
    # 1. Find the latest version number
    latest_version_record = db.query(RFPDraft).filter(RFPDraft.rfp_id == rfp_id).order_by(desc(RFPDraft.version)).first()
    if not latest_version_record:
        return None
    
    latest_version = latest_version_record.version
    
    # 2. Get all records for this version — BUG 4 FIX: always explicitly ORDER BY section_order ASC
    # Repair any wrong/null section_order values before serving to the SA workspace
    try:
        from app.services.generation_service import repair_section_order
        repair_section_order(db, rfp_id, latest_version)
    except Exception:
        pass
    draft_records = db.query(RFPDraft).filter(
        RFPDraft.rfp_id == rfp_id,
        RFPDraft.version == latest_version
    ).order_by(RFPDraft.section_order.asc()).all()
    
    if not draft_records:
        return None
        
    # 3. If only one record and no section name, it's a legacy/single draft
    if len(draft_records) == 1 and not draft_records[0].section_name:
        return draft_records[0]
        
    # 4. Otherwise, aggregate all sections
    full_content = ""
    for dr in draft_records:
        if dr.section_name:
            full_content += f"# {dr.section_name}\n\n"
        full_content += dr.draft_content + "\n\n"
    
    # Return a synthetic object that mimics RFPDraft for compatibility
    class SyntheticDraft:
        def __init__(self, content, version, rfp_id, created_by):
            self.draft_content = content
            self.version = version
            self.rfp_id = rfp_id
            self.created_by = created_by
            self.id = 0 # Dummy ID
            self.is_final = False
            self.created_at = draft_records[0].created_at
            
    return SyntheticDraft(full_content.strip(), latest_version, rfp_id, draft_records[0].created_by)

def get_draft_history(db: Session, rfp_id: int):
    return db.query(RFPDraft).filter(RFPDraft.rfp_id == rfp_id).order_by(desc(RFPDraft.version)).all()
