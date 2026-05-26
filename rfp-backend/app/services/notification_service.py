from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.notification import Notification

def create_notification(db: Session, user_id: int, message: str, rfp_id: int = None, type: str = "info"):
    """
    Creates a notification. Never raises — logs errors but does not break the calling transaction.
    BUG 3 FIX: Uses Python datetime.now(timezone.utc) instead of SQL utcnow() which does not exist in PostgreSQL.
    """
    try:
        notification = Notification(
            user_id=user_id,
            rfp_id=rfp_id,
            message=message,
            type=type,
            created_at=datetime.now(timezone.utc),  # Explicit UTC timestamp from Python
        )
        db.add(notification)
        db.commit()
        db.refresh(notification)
        return notification
    except Exception as e:
        print(f"[notification_service] create_notification failed (non-fatal): {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return None


def get_user_notifications(db: Session, user_id: int, limit: int = 10):
    return db.query(Notification).filter(Notification.user_id == user_id).order_by(Notification.created_at.desc()).limit(limit).all()

def mark_as_read(db: Session, notification_id: int):
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if notification:
        notification.is_read = True
        db.commit()
    return notification

def clear_all(db: Session, user_id: int):
    db.query(Notification).filter(Notification.user_id == user_id).update({"is_read": True})
    db.commit()
    return True
