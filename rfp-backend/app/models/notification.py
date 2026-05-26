from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func
from app.core.database import Base

class Notification(Base):
    __tablename__ = "notifications"
    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"))
    rfp_id      = Column(Integer, ForeignKey("rfp_documents.id"), nullable=True)
    message     = Column(Text, nullable=False)
    is_read     = Column(Boolean, default=False)
    type        = Column(String(50)) # 'info', 'success', 'warning', 'error'
    created_at  = Column(DateTime, default=func.now())  # func.now() is standard SQL, utcnow() does not exist in PostgreSQL
