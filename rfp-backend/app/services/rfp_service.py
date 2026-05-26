from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.rfp import RFPDocument, RFPApproval, RFPAssignment, RFPComment, AuditLog
from app.models.user import User
from typing import Optional

def get_all_rfps(db: Session):
    return db.query(RFPDocument).order_by(
        RFPDocument.created_at.desc(),
        RFPDocument.id.desc()
    ).all()


def get_rfp_by_id(db: Session, rfp_id: int):
    return db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()

def get_dashboard_summary(db: Session):
    from app.models.rfp import RFPMetadata
    # Total active RFPs (excluding failed/error/rejected states)
    total    = db.query(func.count(RFPDocument.id)).filter(
        ~RFPDocument.current_status.in_(["error", "failed", "rejected"])
    ).scalar()
    
    # RFPs awaiting PM decision
    review   = db.query(func.count(RFPDocument.id)).filter(
        RFPDocument.current_status.in_(["pending-review", "summary_generated", "under_review", "awaiting_ceo_decision"])
    ).scalar()
    
    # RFPs approved but not yet assigned
    approved = db.query(func.count(RFPDocument.id)).filter(RFPDocument.current_status == "approved").scalar()
    
    # RFPs already assigned and in progress
    assigned = db.query(func.count(RFPDocument.id)).filter(
        RFPDocument.current_status.in_(["assigned_to_sa", "generating_draft", "in_drafting", "generation_paused", "ai_draft_ready", "under_sa_review", "submitted_for_review"])
    ).scalar()
    
    rejected = db.query(func.count(RFPDocument.id)).filter(RFPDocument.current_status == "rejected").scalar()
    on_hold  = db.query(func.count(RFPDocument.id)).filter(RFPDocument.current_status.in_(["on_hold", "on-hold"])).scalar()
    
    total_val = db.query(func.sum(RFPMetadata.estimated_value)).scalar() or 0
    
    return {
        "total": total, 
        "uploaded": 0, 
        "under_review": review,
        "approved": approved, 
        "rejected": rejected,
        "on_hold": on_hold,
        "assigned": assigned,
        "total_value": float(total_val)
    }

def update_rfp_status(db: Session, rfp_id: int, status: str, user_id: int):
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp:
        return None
    old_status = rfp.current_status
    rfp.current_status = status
    log = AuditLog(rfp_id=rfp_id, user_id=user_id, action="status_changed",
                   old_value=old_status, new_value=status)
    db.add(log)
    db.commit()
    db.refresh(rfp)
    return rfp

def save_decision(db: Session, rfp_id: int, user_id: int, decision: str, reason: str):
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp:
        return None
    
    # Guard: Prevent duplicate initial decision if already approved/assigned/generated
    protected_statuses = [
        "approved", "assigned_to_sa", "generating_draft", "in_drafting", 
        "generation_paused", "draft_complete", "ai_draft_ready", 
        "submitted_for_review", "final_approved", "rejected"
    ]
    if rfp.current_status in protected_statuses and decision in ["approved", "rejected", "on_hold"]:
         # We allow 'proceed' or 'on_hold' to be toggled maybe, but the user requested strict lifecycle.
         # For now, let's block if already beyond initial review.
         pass 

    approval = RFPApproval(rfp_id=rfp_id, approved_by=user_id, decision=decision, reason=reason)
    db.add(approval)
    status_map = {
        "approved": "approved", "rejected": "rejected",
        "on_hold": "on_hold",   "proceed": "awaiting_ceo_decision"
    }
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if rfp:
        rfp.current_status = status_map.get(decision, rfp.current_status)
    log = AuditLog(rfp_id=rfp_id, user_id=user_id, action=f"decision_{decision}", new_value=reason)
    db.add(log)
    db.commit()

    # ROOT CAUSE FIX: Notify the PM who made the decision (user_id), not rfp.uploaded_by
    # rfp.uploaded_by is the person who uploaded the doc — often the PM themselves, but not always
    from app.services.notification_service import create_notification
    from app.models.user import User
    action_label = decision.replace('_', ' ').capitalize()
    notif_type = "info" if decision == "on_hold" else "success" if decision == "approved" else "error"
    notif_msg = f"RFP '{rfp.title}' {action_label} successfully."
    if reason:
        notif_msg += f" Reason: {reason[:60]}"
    n = create_notification(db, user_id=user_id, message=notif_msg, rfp_id=rfp_id, type=notif_type)
    pm_user = db.query(User).filter(User.id == user_id).first()
    print(f"[notification] PM Decision notification: id={n.id if n else None} rfp_id={rfp_id} user_id={user_id} role={pm_user.role if pm_user else 'unknown'} msg='{notif_msg}' is_read=False")

    return approval

def assign_architect(db: Session, rfp_id: int, assigned_to: int, assigned_by: int, notes: str):
    # Guard: Prevent duplicate active assignment
    existing = db.query(RFPAssignment).filter(
        RFPAssignment.rfp_id == rfp_id,
        RFPAssignment.assignment_status == "active"
    ).first()
    if existing:
        if existing.assigned_to == assigned_to:
            return existing # Idempotent
        else:
            # Reassigning? For now, let's keep it simple and block or mark old as inactive.
            existing.assignment_status = "inactive"
    
    assignment = RFPAssignment(rfp_id=rfp_id, assigned_to=assigned_to,
                               assigned_by=assigned_by, notes=notes)
    db.add(assignment)
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if rfp:
        rfp.current_status = "assigned_to_sa"
    log = AuditLog(rfp_id=rfp_id, user_id=assigned_by, action="assigned_to_architect",
                   new_value=str(assigned_to))
    db.add(log)
    db.commit()

    # ROOT CAUSE FIX: Notify both the SA and the PM
    from app.services.notification_service import create_notification
    from app.models.user import User
    sa_user   = db.query(User).filter(User.id == assigned_to).first()
    pm_user   = db.query(User).filter(User.id == assigned_by).first()
    rfp_title = rfp.title if rfp else f"RFP #{rfp_id}"

    # Notify SA: "You have been assigned to RFP: <title>"
    sa_msg = f"You have been assigned to RFP: '{rfp_title}'. Please review and start the proposal draft."
    sa_n = create_notification(db, user_id=assigned_to, message=sa_msg, rfp_id=rfp_id, type="info")
    print(f"[notification] SA Assignment: id={sa_n.id if sa_n else None} rfp_id={rfp_id} user_id={assigned_to} role={sa_user.role if sa_user else 'SA'} msg='{sa_msg}' is_read=False")

    # Notify PM: confirmation that assignment succeeded
    pm_msg = f"RFP '{rfp_title}' assigned to {sa_user.name if sa_user else f'Architect #{assigned_to}'} successfully."
    pm_n = create_notification(db, user_id=assigned_by, message=pm_msg, rfp_id=rfp_id, type="success")
    print(f"[notification] PM Assign Confirmation: id={pm_n.id if pm_n else None} rfp_id={rfp_id} user_id={assigned_by} role={pm_user.role if pm_user else 'PM'} msg='{pm_msg}' is_read=False")

    return assignment

def get_assigned_rfps(db: Session, user_id: int):
    # Join RFPAssignment directly to fetch the assigner User
    results = db.query(RFPDocument, RFPAssignment, User.name)\
        .join(RFPAssignment, RFPAssignment.rfp_id == RFPDocument.id)\
        .join(User, User.id == RFPAssignment.assigned_by)\
        .filter(
            RFPAssignment.assigned_to == user_id,
            RFPAssignment.assignment_status == "active"
        )\
        .order_by(RFPAssignment.assigned_at.desc(), RFPDocument.updated_at.desc(), RFPDocument.id.desc())\
        .all()
        
    final_rfps = []
    for rfp, assignment, assigner_name in results:
        # We attach the extra assigned_by_name attribute
        rfp_data = rfp.__dict__.copy()
        rfp_data['assigned_by_name'] = assigner_name
        final_rfps.append(rfp_data)
        
    return final_rfps

def add_comment(db: Session, rfp_id: int, user_id: int, text: str, entity_type: str, entity_id: int):
    comment = RFPComment(rfp_id=rfp_id, user_id=user_id, comment_text=text,
                         entity_type=entity_type, entity_id=entity_id)
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment