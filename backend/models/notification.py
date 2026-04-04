# backend/models/notification.py
"""
Notification System Models
Handles SMS, WhatsApp, and email notifications
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.orm import relationship
from ..core.database import Base
from datetime import datetime


class NotificationTemplate(Base):
    """Configurable notification templates"""
    __tablename__ = "notification_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    sacco_id = Column(Integer, ForeignKey("saccos.id"), nullable=False)
    name = Column(String(100), nullable=False)  # e.g., "welcome", "loan_reminder"
    channel = Column(String(20), nullable=False)  # sms, whatsapp, email
    subject = Column(String(255), nullable=True)
    message = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    sacco = relationship("Sacco", foreign_keys=[sacco_id])


class NotificationLog(Base):
    """Log of all sent notifications"""
    __tablename__ = "notification_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sacco_id = Column(Integer, ForeignKey("saccos.id"), nullable=False)
    template_id = Column(Integer, ForeignKey("notification_templates.id"), nullable=True)
    channel = Column(String(20), nullable=False)
    recipient = Column(String(100), nullable=False)
    subject = Column(String(255), nullable=True)
    message = Column(Text, nullable=False)
    status = Column(String(20), default="pending")  # pending, sent, failed
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    sacco = relationship("Sacco", foreign_keys=[sacco_id])
    template = relationship("NotificationTemplate", foreign_keys=[template_id])