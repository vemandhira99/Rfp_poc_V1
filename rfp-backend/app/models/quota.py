from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func
from app.core.database import Base

class QuotaUsage(Base):
    __tablename__ = "quota_usage"

    id         = Column(Integer, primary_key=True, index=True)
    day        = Column(String(10), unique=True, index=True) # YYYY-MM-DD
    request_count = Column(Integer, default=0)
    token_count   = Column(Integer, default=0)
    is_exhausted  = Column(Boolean, default=False)
    updated_at    = Column(DateTime, default=func.now(), onupdate=func.now())
