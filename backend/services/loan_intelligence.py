# backend/services/loan_intelligence.py
"""
Loan Intelligence Service
Handles risk scoring, eligibility, and repayment schedules
"""
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, timedelta
import logging
from typing import List, Dict, Any, Optional

from ..models import User, Loan, LoanPayment, Saving

logger = logging.getLogger(__name__)


class LoanIntelligenceService:
    """Service for loan intelligence features"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def calculate_eligibility_score(self, user_id: int) -> Dict[str, Any]:
        """Calculate loan eligibility score for a member"""
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"score": 0, "eligible": False, "factors": []}
        
        score = 0
        factors = []
        
        # Factor 1: Savings history (max 40 points)
        savings = self.db.query(Saving).filter(
            Saving.user_id == user_id,
            Saving.type == "deposit"
        ).all()
        
        total_savings = sum(s.amount for s in savings)
        if total_savings >= 1000000:
            score += 40
            factors.append({"factor": "Savings balance", "score": 40, "value": f"UGX {total_savings:,.2f}"})
        elif total_savings >= 500000:
            score += 30
            factors.append({"factor": "Savings balance", "score": 30, "value": f"UGX {total_savings:,.2f}"})
        elif total_savings >= 100000:
            score += 20
            factors.append({"factor": "Savings balance", "score": 20, "value": f"UGX {total_savings:,.2f}"})
        else:
            score += 10
            factors.append({"factor": "Savings balance", "score": 10, "value": f"UGX {total_savings:,.2f}"})
        
        # Factor 2: Savings consistency (max 30 points)
        if len(savings) >= 12:
            score += 30
            factors.append({"factor": "Regular saver", "score": 30, "value": f"{len(savings)} transactions"})
        elif len(savings) >= 6:
            score += 20
            factors.append({"factor": "Regular saver", "score": 20, "value": f"{len(savings)} transactions"})
        elif len(savings) >= 3:
            score += 10
            factors.append({"factor": "Regular saver", "score": 10, "value": f"{len(savings)} transactions"})
        else:
            factors.append({"factor": "Regular saver", "score": 0, "value": f"{len(savings)} transactions"})
        
        # Factor 3: Previous loan performance (max 30 points)
        previous_loans = self.db.query(Loan).filter(
            Loan.user_id == user_id,
            Loan.status.in_(["completed", "approved"])
        ).all()
        
        if previous_loans:
            perfect_repayments = 0
            for loan in previous_loans:
                payments = self.db.query(LoanPayment).filter(
                    LoanPayment.loan_id == loan.id
                ).all()
                total_paid = sum(p.amount for p in payments)
                if total_paid >= loan.total_payable:
                    perfect_repayments += 1
            
            if perfect_repayments == len(previous_loans):
                score += 30
                factors.append({"factor": "Perfect repayment history", "score": 30, "value": f"{len(previous_loans)} loans"})
            elif perfect_repayments > 0:
                score += 20
                factors.append({"factor": "Good repayment history", "score": 20, "value": f"{perfect_repayments}/{len(previous_loans)} loans"})
            else:
                score += 5
                factors.append({"factor": "Previous loan issues", "score": 5, "value": "Late payments detected"})
        else:
            score += 15
            factors.append({"factor": "First-time borrower", "score": 15, "value": "No loan history"})
        
        eligible = score >= 50
        
        return {
            "score": score,
            "eligible": eligible,
            "max_loan_amount": total_savings * 3 if eligible else 0,
            "factors": factors
        }
    
    def calculate_risk_score(self, loan_id: int) -> Dict[str, Any]:
        """Calculate risk score for a specific loan"""
        loan = self.db.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            return {"score": 0, "level": "unknown", "factors": []}
        
        risk_score = 0
        factors = []
        
        # Factor 1: Payment history (max 40 points to risk)
        payments = self.db.query(LoanPayment).filter(
            LoanPayment.loan_id == loan_id
        ).order_by(LoanPayment.timestamp.desc()).all()
        
        if not payments:
            # No payments made
            days_since_approval = (datetime.utcnow() - loan.approved_at).days if loan.approved_at else 0
            if days_since_approval > 30:
                risk_score += 40
                factors.append({"factor": "No payments made", "risk_contribution": 40, "value": f"{days_since_approval} days"})
            else:
                risk_score += 20
                factors.append({"factor": "No payments yet", "risk_contribution": 20, "value": f"Approved {days_since_approval} days ago"})
        else:
            # Check for late payments
            expected_payments = (datetime.utcnow() - loan.approved_at).days // 30 if loan.approved_at else 0
            actual_payments = len(payments)
            
            if actual_payments < expected_payments:
                missed = expected_payments - actual_payments
                risk_score += min(30, missed * 10)
                factors.append({"factor": "Missed payments", "risk_contribution": min(30, missed * 10), "value": f"{missed} payment(s) missed"})
            
            # Check last payment recency
            last_payment = payments[0]
            days_since_last = (datetime.utcnow() - last_payment.timestamp).days
            if days_since_last > 45:
                risk_score += 30
                factors.append({"factor": "No recent payment", "risk_contribution": 30, "value": f"{days_since_last} days"})
            elif days_since_last > 30:
                risk_score += 15
                factors.append({"factor": "Payment approaching due", "risk_contribution": 15, "value": f"{days_since_last} days"})
        
        # Factor 2: Loan amount relative to savings (max 30 points)
        total_savings = self.db.query(func.sum(Saving.amount)).filter(
            Saving.user_id == loan.user_id,
            Saving.type == "deposit"
        ).scalar() or 0
        
        if total_savings > 0:
            ratio = loan.amount / total_savings
            if ratio > 5:
                risk_score += 30
                factors.append({"factor": "High loan-to-savings ratio", "risk_contribution": 30, "value": f"{ratio:.1f}x savings"})
            elif ratio > 3:
                risk_score += 15
                factors.append({"factor": "Moderate loan-to-savings ratio", "risk_contribution": 15, "value": f"{ratio:.1f}x savings"})
        
        # Determine risk level
        if risk_score >= 60:
            risk_level = "high"
        elif risk_score >= 30:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        # Update loan with risk assessment
        loan.risk_score = risk_score
        loan.risk_level = risk_level
        loan.last_risk_assessment = datetime.utcnow()
        self.db.commit()
        
        return {
            "score": risk_score,
            "level": risk_level,
            "factors": factors
        }
    
    def generate_repayment_schedule(self, loan_id: int) -> List[Dict[str, Any]]:
        """Generate repayment schedule for a loan"""
        loan = self.db.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            return []
        
        monthly_payment = loan.calculate_monthly_payment()
        schedule = []
        
        start_date = loan.approved_at or loan.timestamp or datetime.utcnow()
        remaining_balance = loan.total_payable
        
        for i in range(loan.term):
            due_date = start_date + timedelta(days=30 * (i + 1))
            payment = monthly_payment
            
            if i == loan.term - 1:
                # Last payment adjusts for rounding
                payment = remaining_balance
            
            schedule.append({
                "installment": i + 1,
                "due_date": due_date.isoformat(),
                "amount": payment,
                "status": "pending",
                "remaining_balance": remaining_balance - payment
            })
            
            remaining_balance -= payment
        
        # Save schedule to loan
        loan.repayment_schedule = schedule
        self.db.commit()
        
        return schedule
    
    def get_early_warnings(self, sacco_id: int) -> List[Dict[str, Any]]:
        """Get loans with early warning signs"""
        active_loans = self.db.query(Loan).filter(
            Loan.sacco_id == sacco_id,
            Loan.status.in_(["approved", "partial"])
        ).all()
        
        warnings = []
        for loan in active_loans:
            risk_assessment = self.calculate_risk_score(loan.id)
            
            if risk_assessment["level"] == "high":
                warnings.append({
                    "loan_id": loan.id,
                    "member_name": loan.user.full_name if loan.user else "Unknown",
                    "amount": loan.amount,
                    "risk_score": risk_assessment["score"],
                    "risk_level": risk_assessment["level"],
                    "factors": risk_assessment["factors"],
                    "outstanding": loan.total_payable - (loan.total_paid or 0)
                })
        
        return sorted(warnings, key=lambda x: x["risk_score"], reverse=True)
    
    def get_loan_portfolio_risk_summary(self, sacco_id: int) -> Dict[str, Any]:
        """Get summary of loan portfolio risk"""
        loans = self.db.query(Loan).filter(Loan.sacco_id == sacco_id).all()
        
        total_loans = len(loans)
        total_amount = sum(l.amount for l in loans)
        
        risk_counts = {"low": 0, "medium": 0, "high": 0}
        risk_amounts = {"low": 0, "medium": 0, "high": 0}
        
        for loan in loans:
            if loan.risk_level == "low":
                risk_counts["low"] += 1
                risk_amounts["low"] += loan.amount
            elif loan.risk_level == "medium":
                risk_counts["medium"] += 1
                risk_amounts["medium"] += loan.amount
            else:
                risk_counts["high"] += 1
                risk_amounts["high"] += loan.amount
        
        return {
            "total_loans": total_loans,
            "total_amount": total_amount,
            "risk_distribution": {
                "low": {"count": risk_counts["low"], "amount": risk_amounts["low"], "percentage": (risk_counts["low"]/total_loans*100) if total_loans > 0 else 0},
                "medium": {"count": risk_counts["medium"], "amount": risk_amounts["medium"], "percentage": (risk_counts["medium"]/total_loans*100) if total_loans > 0 else 0},
                "high": {"count": risk_counts["high"], "amount": risk_amounts["high"], "percentage": (risk_counts["high"]/total_loans*100) if total_loans > 0 else 0}
            }
        }