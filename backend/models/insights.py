# backend/models/insights.py
"""
Smart SACCO Insights Engine Models
Tracks insights, alerts, and analytics data
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Text, Boolean
from sqlalchemy.orm import relationship
from ..core.database import Base
from datetime import datetime
import enum


class InsightType(str, enum.Enum):
    """Types of insights generated"""
    INACTIVE_SAVERS = "inactive_savers"
    LIKELY_DEFAULTERS = "likely_defaulters"
    TOP_SAVERS = "top_savers"
    MOST_ACTIVE = "most_active"
    IRREGULAR_SAVINGS = "irregular_savings"
    HIGH_RISK_LOANS = "high_risk_loans"
    ENGAGEMENT_DROPS = "engagement_drops"
    GROWTH_SPIKES = "growth_spikes"


class AlertSeverity(str, enum.Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class InsightLog(Base):
    """Stores generated insights for historical tracking"""
    __tablename__ = "insight_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    sacco_id = Column(Integer, ForeignKey("saccos.id"), nullable=False)
    insight_type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    data = Column(JSON)  # Stores list of member IDs or relevant data
    severity = Column(String(20), default="info")
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    sacco = relationship("Sacco", foreign_keys=[sacco_id])
    resolver = relationship("User", foreign_keys=[resolved_by])


class AlertRule(Base):
    """Configurable alert rules for insights"""
    __tablename__ = "alert_rules"
    
    id = Column(Integer, primary_key=True, index=True)
    sacco_id = Column(Integer, ForeignKey("saccos.id"), nullable=False)
    rule_name = Column(String(100), nullable=False)
    insight_type = Column(String(50), nullable=False)
    threshold_days = Column(Integer, default=30)  # Days of inactivity
    threshold_amount = Column(Float, nullable=True)  # For irregular savings
    is_active = Column(Boolean, default=True)
    notify_admin = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    sacco = relationship("Sacco", foreign_keys=[sacco_id])


class WeeklySummary(Base):
    """Weekly auto-generated summaries"""
    __tablename__ = "weekly_summaries"
    
    id = Column(Integer, primary_key=True, index=True)
    sacco_id = Column(Integer, ForeignKey("saccos.id"), nullable=False)
    week_start = Column(DateTime, nullable=False)
    week_end = Column(DateTime, nullable=False)
    summary_data = Column(JSON, nullable=False)  # Full summary as JSON
    sent_at = Column(DateTime, nullable=True)  # When email was sent
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    sacco = relationship("Sacco", foreign_keys=[sacco_id])