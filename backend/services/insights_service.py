# backend/services/insights_service.py
"""
Smart Insights Service Layer
Generates actionable insights from SACCO data
"""
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from datetime import datetime, timedelta
import logging
from typing import List, Dict, Any

from ..models import User, Saving, Loan, LoanPayment, Sacco
from ..models.insights import InsightLog, AlertRule, InsightType, AlertSeverity, WeeklySummary

logger = logging.getLogger(__name__)


class InsightsService:
    """Service for generating and managing insights"""
    
    def __init__(self, db: Session, sacco_id: int):
        self.db = db
        self.sacco_id = sacco_id
    
    def generate_all_insights(self) -> List[Dict[str, Any]]:
        """Generate all types of insights"""
        insights = []
        
        # Generate each insight type
        insights.extend(self.detect_inactive_savers())
        insights.extend(self.detect_likely_defaulters())
        insights.extend(self.get_top_savers())
        insights.extend(self.get_most_active_members())
        insights.extend(self.detect_irregular_savings())
        
        # Save insights to database
        for insight in insights:
            self.save_insight(insight)
        
        return insights
    
    def detect_inactive_savers(self, days_threshold: int = 30) -> List[Dict[str, Any]]:
        """Identify members who haven't saved in X days"""
        cutoff_date = datetime.utcnow() - timedelta(days=days_threshold)
        
        # Get all members
        members = self.db.query(User).filter(
            User.sacco_id == self.sacco_id,
            User.role == "MEMBER",
            User.is_active == True
        ).all()
        
        inactive_members = []
        for member in members:
            # Get last saving
            last_saving = self.db.query(Saving).filter(
                Saving.user_id == member.id,
                Saving.type == "deposit"
            ).order_by(Saving.timestamp.desc()).first()
            
            if not last_saving or last_saving.timestamp < cutoff_date:
                days_inactive = (datetime.utcnow() - (last_saving.timestamp if last_saving else member.created_at)).days
                inactive_members.append({
                    "user_id": member.id,
                    "name": member.full_name or member.email,
                    "days_inactive": days_inactive,
                    "last_saving_date": last_saving.timestamp if last_saving else None
                })
        
        if inactive_members:
            return [{
                "type": InsightType.INACTIVE_SAVERS,
                "title": f"{len(inactive_members)} Inactive Savers Detected",
                "description": f"Members who haven't saved in the last {days_threshold} days",
                "data": inactive_members,
                "severity": AlertSeverity.WARNING
            }]
        return []
    
    def detect_likely_defaulters(self) -> List[Dict[str, Any]]:
        """Identify members likely to default based on repayment patterns"""
        # Get all active loans
        active_loans = self.db.query(Loan).filter(
            Loan.sacco_id == self.sacco_id,
            Loan.status.in_(["approved", "partial"])
        ).all()
        
        likely_defaulters = []
        for loan in active_loans:
            # Check repayment patterns
            payments = self.db.query(LoanPayment).filter(
                LoanPayment.loan_id == loan.id
            ).order_by(LoanPayment.timestamp.desc()).all()
            
            risk_score = 0
            reasons = []
            
            if not payments:
                # No payments made
                days_since_approval = (datetime.utcnow() - loan.approved_at).days if loan.approved_at else 0
                if days_since_approval > 30:
                    risk_score += 40
                    reasons.append("No payments made since approval")
            else:
                # Check for late payments
                expected_payments = (datetime.utcnow() - loan.approved_at).days // 30 if loan.approved_at else 0
                actual_payments = len(payments)
                
                if actual_payments < expected_payments:
                    missed_payments = expected_payments - actual_payments
                    risk_score += min(30, missed_payments * 10)
                    reasons.append(f"Missed {missed_payments} payment(s)")
                
                # Check last payment date
                last_payment = payments[0]
                days_since_last = (datetime.utcnow() - last_payment.timestamp).days
                if days_since_last > 45:
                    risk_score += 30
                    reasons.append(f"No payment for {days_since_last} days")
            
            if risk_score >= 50:
                likely_defaulters.append({
                    "loan_id": loan.id,
                    "user_id": loan.user_id,
                    "amount": loan.amount,
                    "risk_score": risk_score,
                    "reasons": reasons,
                    "member_name": loan.user.full_name if loan.user else None
                })
        
        if likely_defaulters:
            return [{
                "type": InsightType.LIKELY_DEFAULTERS,
                "title": f"{len(likely_defaulters)} Members at Risk of Default",
                "description": "Members showing signs of potential loan default",
                "data": likely_defaulters,
                "severity": AlertSeverity.CRITICAL
            }]
        return []
    
    def get_top_savers(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top savers in the SACCO"""
        # Aggregate savings by user
        top_savers = self.db.query(
            User.id,
            User.full_name,
            User.email,
            func.sum(Saving.amount).label("total_savings")
        ).join(
            Saving, Saving.user_id == User.id
        ).filter(
            User.sacco_id == self.sacco_id,
            User.role == "MEMBER",
            Saving.type == "deposit"
        ).group_by(
            User.id
        ).order_by(
            func.sum(Saving.amount).desc()
        ).limit(limit).all()
        
        if top_savers:
            data = [{
                "user_id": t[0],
                "name": t[1] or t[2],
                "total_savings": float(t[3])
            } for t in top_savers]
            
            return [{
                "type": InsightType.TOP_SAVERS,
                "title": f"Top {len(top_savers)} Savers",
                "description": "Members with highest savings balances",
                "data": data,
                "severity": AlertSeverity.INFO
            }]
        return []
    
    def get_most_active_members(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Identify most active members based on login and transaction frequency"""
        # Get recent logins (assuming we track in logs)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        # Count transactions per member
        active_members = self.db.query(
            User.id,
            User.full_name,
            User.email,
            func.count(Saving.id).label("transaction_count")
        ).join(
            Saving, Saving.user_id == User.id
        ).filter(
            User.sacco_id == self.sacco_id,
            User.role == "MEMBER",
            Saving.timestamp >= thirty_days_ago
        ).group_by(
            User.id
        ).order_by(
            func.count(Saving.id).desc()
        ).limit(limit).all()
        
        if active_members:
            data = [{
                "user_id": t[0],
                "name": t[1] or t[2],
                "transaction_count": t[3]
            } for t in active_members]
            
            return [{
                "type": InsightType.MOST_ACTIVE,
                "title": f"Top {len(active_members)} Active Members",
                "description": "Members with most transactions in last 30 days",
                "data": data,
                "severity": AlertSeverity.INFO
            }]
        return []
    
    def detect_irregular_savings(self) -> List[Dict[str, Any]]:
        """Detect irregular savings patterns (large fluctuations)"""
        # Get all members with savings
        members = self.db.query(User).filter(
            User.sacco_id == self.sacco_id,
            User.role == "MEMBER"
        ).all()
        
        irregular_members = []
        for member in members:
            # Get last 5 savings
            savings = self.db.query(Saving).filter(
                Saving.user_id == member.id,
                Saving.type == "deposit"
            ).order_by(Saving.timestamp.desc()).limit(5).all()
            
            if len(savings) >= 3:
                amounts = [s.amount for s in savings]
                avg_amount = sum(amounts) / len(amounts)
                variance = sum((a - avg_amount) ** 2 for a in amounts) / len(amounts)
                
                # High variance indicates irregular savings
                if variance > (avg_amount * 0.5):  # 50% variance threshold
                    irregular_members.append({
                        "user_id": member.id,
                        "name": member.full_name or member.email,
                        "average_saving": avg_amount,
                        "variance": variance,
                        "savings": amounts
                    })
        
        if irregular_members:
            return [{
                "type": InsightType.IRREGULAR_SAVINGS,
                "title": f"{len(irregular_members)} Members with Irregular Savings",
                "description": "Members showing inconsistent saving patterns",
                "data": irregular_members,
                "severity": AlertSeverity.WARNING
            }]
        return []
    
    def save_insight(self, insight: Dict[str, Any]) -> InsightLog:
        """Save insight to database"""
        insight_log = InsightLog(
            sacco_id=self.sacco_id,
            insight_type=insight["type"],
            title=insight["title"],
            description=insight["description"],
            data=insight["data"],
            severity=insight.get("severity", "info")
        )
        self.db.add(insight_log)
        self.db.commit()
        self.db.refresh(insight_log)
        return insight_log
    
    def get_active_alerts(self, limit: int = 50) -> List[InsightLog]:
        """Get unresolved insights as alerts"""
        return self.db.query(InsightLog).filter(
            InsightLog.sacco_id == self.sacco_id,
            InsightLog.is_resolved == False,
            InsightLog.severity.in_(["warning", "critical"])
        ).order_by(
            InsightLog.generated_at.desc()
        ).limit(limit).all()
    
    def resolve_alert(self, alert_id: int, resolved_by: int) -> bool:
        """Mark an alert as resolved"""
        alert = self.db.query(InsightLog).filter(
            InsightLog.id == alert_id,
            InsightLog.sacco_id == self.sacco_id
        ).first()
        
        if alert:
            alert.is_resolved = True
            alert.resolved_at = datetime.utcnow()
            alert.resolved_by = resolved_by
            self.db.commit()
            return True
        return False
    
    def generate_weekly_summary(self) -> Dict[str, Any]:
        """Generate weekly summary of SACCO activities"""
        week_start = datetime.utcnow() - timedelta(days=7)
        
        # Calculate weekly metrics
        new_members = self.db.query(User).filter(
            User.sacco_id == self.sacco_id,
            User.created_at >= week_start
        ).count()
        
        new_savings = self.db.query(Saving).filter(
            Saving.sacco_id == self.sacco_id,
            Saving.timestamp >= week_start,
            Saving.type == "deposit"
        ).all()
        total_new_savings = sum(s.amount for s in new_savings)
        
        new_loans = self.db.query(Loan).filter(
            Loan.sacco_id == self.sacco_id,
            Loan.timestamp >= week_start
        ).count()
        
        total_loans_amount = self.db.query(func.sum(Loan.amount)).filter(
            Loan.sacco_id == self.sacco_id,
            Loan.timestamp >= week_start
        ).scalar() or 0
        
        # Get top insights for the week
        insights = self.generate_all_insights()
        
        summary = {
            "week_start": week_start.isoformat(),
            "week_end": datetime.utcnow().isoformat(),
            "metrics": {
                "new_members": new_members,
                "new_savings_count": len(new_savings),
                "total_new_savings": total_new_savings,
                "new_loans": new_loans,
                "total_loans_amount": total_loans_amount
            },
            "top_insights": insights[:3] if insights else []
        }
        
        # Save summary
        weekly_summary = WeeklySummary(
            sacco_id=self.sacco_id,
            week_start=week_start,
            week_end=datetime.utcnow(),
            summary_data=summary
        )
        self.db.add(weekly_summary)
        self.db.commit()
        
        return summary