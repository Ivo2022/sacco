from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, Boolean
from sqlalchemy.orm import relationship
from ..core.database import Base
from datetime import datetime
import enum

class MembershipStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"

class MembershipFee(Base):
    """Membership fee payments"""
    __tablename__ = "membership_fees"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sacco_id = Column(Integer, ForeignKey("saccos.id"), nullable=False)
    amount = Column(Float, nullable=False)
    payment_method = Column(String(50), nullable=False)
    reference_number = Column(String(100), nullable=True)
    status = Column(String(20), default="pending")  # pending, approved, rejected
    paid_at = Column(DateTime, default=datetime.utcnow)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    membership_number = Column(String(50), unique=True, nullable=True)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    sacco = relationship("Sacco", foreign_keys=[sacco_id])
    approver = relationship("User", foreign_keys=[approved_by])

class MembershipApplication(Base):
    """Membership application tracking"""
    __tablename__ = "membership_applications"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sacco_id = Column(Integer, ForeignKey("saccos.id"), nullable=False)
    application_date = Column(DateTime, default=datetime.utcnow)
    status = Column(Enum(MembershipStatus), default=MembershipStatus.PENDING)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejection_reason = Column(String(500), nullable=True)
    membership_number = Column(String(50), unique=True, nullable=True)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    sacco = relationship("Sacco", foreign_keys=[sacco_id])
    approver = relationship("User", foreign_keys=[approved_by])