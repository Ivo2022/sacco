# backend/models/share.py
"""
Share Capital Models
Handles share types, share holdings, and share transactions
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Enum as SQLEnum
from sqlalchemy.orm import relationship
from ..core.database import Base
from datetime import datetime
import enum


class ShareTransactionType(str, enum.Enum):
    """Types of share transactions"""
    SUBSCRIPTION = "subscription"      # Buying shares
    TRANSFER = "transfer"              # Transferring shares
    WITHDRAWAL = "withdrawal"          # Selling shares back to SACCO
    DIVIDEND_REINVESTMENT = "dividend_reinvestment"


class ShareClass(str, enum.Enum):
    """Share classes/categories"""
    CLASS_A = "class_a"   # Voting shares
    CLASS_B = "class_b"   # Non-voting shares
    CLASS_C = "class_c"   # Employee shares


class ShareType(Base):
    """Share types/categories"""
    __tablename__ = "share_types"
    
    id = Column(Integer, primary_key=True, index=True)
    sacco_id = Column(Integer, ForeignKey("saccos.id"), nullable=False)
    name = Column(String(100), nullable=False)
    class_type = Column(SQLEnum(ShareClass), default=ShareClass.CLASS_A)
    par_value = Column(Float, nullable=False)
    minimum_shares = Column(Integer, default=1)
    maximum_shares = Column(Integer, nullable=True)
    is_voting = Column(Boolean, default=True)
    dividend_rate = Column(Float, default=0.0)
    
    # Relationships
    sacco = relationship("Sacco", back_populates="share_types")
    shares = relationship("Share", back_populates="share_type", cascade="all, delete-orphan")


class Share(Base):
    """Individual share holdings"""
    __tablename__ = "shares"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sacco_id = Column(Integer, ForeignKey("saccos.id"), nullable=False)
    share_type_id = Column(Integer, ForeignKey("share_types.id"), nullable=False)
    quantity = Column(Integer, default=0)
    total_value = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    sacco = relationship("Sacco")
    share_type = relationship("ShareType", back_populates="shares")
    transactions = relationship("ShareTransaction", back_populates="share", cascade="all, delete-orphan")


class ShareTransaction(Base):
    """Share purchase/sale transactions"""
    __tablename__ = "share_transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    share_id = Column(Integer, ForeignKey("shares.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sacco_id = Column(Integer, ForeignKey("saccos.id"), nullable=False)
    transaction_type = Column(SQLEnum(ShareTransactionType), nullable=False)
    quantity = Column(Integer, nullable=False)
    price_per_share = Column(Float, nullable=False)
    total_amount = Column(Float, nullable=False)
    payment_method = Column(String(50), nullable=True)
    reference_number = Column(String(100), nullable=True)
    transaction_date = Column(DateTime, default=datetime.utcnow)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    notes = Column(String(500), nullable=True)
    
    # Relationships
    share = relationship("Share", back_populates="transactions")
    user = relationship("User", foreign_keys=[user_id])
    sacco = relationship("Sacco")
    approver = relationship("User", foreign_keys=[approved_by])


class DividendDeclaration(Base):
    """Dividend declarations"""
    __tablename__ = "dividend_declarations"
    
    id = Column(Integer, primary_key=True, index=True)
    sacco_id = Column(Integer, ForeignKey("saccos.id"), nullable=False)
    share_type_id = Column(Integer, ForeignKey("share_types.id"), nullable=True)
    declared_date = Column(DateTime, default=datetime.utcnow)
    fiscal_year = Column(Integer, nullable=False)
    rate = Column(Float, nullable=False)
    amount_per_share = Column(Float, nullable=False, default=0.0)
    total_dividend_pool = Column(Float, nullable=False)
    payment_date = Column(DateTime, nullable=True)
    declared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(20), default="pending")
    
    # Relationships
    sacco = relationship("Sacco")
    share_type = relationship("ShareType")
    declarer = relationship("User", foreign_keys=[declared_by])
    payments = relationship("DividendPayment", back_populates="declaration", cascade="all, delete-orphan")


class DividendPayment(Base):
    """Individual dividend payments to members"""
    __tablename__ = "dividend_payments"
    
    id = Column(Integer, primary_key=True, index=True)
    declaration_id = Column(Integer, ForeignKey("dividend_declarations.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sacco_id = Column(Integer, ForeignKey("saccos.id"), nullable=False)
    share_id = Column(Integer, ForeignKey("shares.id"), nullable=False)
    shares_held = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False)
    payment_method = Column(String(50), nullable=True)
    paid_at = Column(DateTime, default=datetime.utcnow)
    reference_number = Column(String(100), nullable=True)
    is_reinvested = Column(Boolean, default=False)
    
    # Relationships
    declaration = relationship("DividendDeclaration", back_populates="payments")
    user = relationship("User")
    sacco = relationship("Sacco")
    share = relationship("Share")