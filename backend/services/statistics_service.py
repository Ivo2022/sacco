# backend/services/statistics_service.py
"""
Statistics service for aggregating data across the system
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from .. import models
from ..models import RoleEnum, PaymentMethodEnum


def get_sacco_statistics(db: Session, sacco_id: int) -> dict:
    """
    Get comprehensive statistics for a SACCO
    
    Args:
        db: Database session
        sacco_id: ID of the SACCO
    
    Returns:
        Dictionary with various statistics
    """
    
    # Member statistics
    total_members = db.query(models.User).filter(
        models.User.sacco_id == sacco_id,
        models.User.role == RoleEnum.MEMBER
    ).count()
    
    active_members = db.query(models.User).filter(
        models.User.sacco_id == sacco_id,
        models.User.role == RoleEnum.MEMBER,
        models.User.is_active == True
    ).count()
    
    # Staff statistics
    total_staff = db.query(models.User).filter(
        models.User.sacco_id == sacco_id,
        models.User.is_staff == True
    ).count()
    
    managers = db.query(models.User).filter(
        models.User.sacco_id == sacco_id,
        models.User.role == RoleEnum.MANAGER
    ).count()
    
    accountants = db.query(models.User).filter(
        models.User.sacco_id == sacco_id,
        models.User.role == RoleEnum.ACCOUNTANT
    ).count()
    
    credit_officers = db.query(models.User).filter(
        models.User.sacco_id == sacco_id,
        models.User.role == RoleEnum.CREDIT_OFFICER
    ).count()
    
    # Savings statistics
    total_deposits = db.query(func.coalesce(func.sum(models.Saving.amount), 0)).filter(
        models.Saving.sacco_id == sacco_id,
        models.Saving.type == 'deposit',
        models.Saving.approved_by.isnot(None)
    ).scalar() or 0
    
    total_withdrawals = db.query(func.coalesce(func.sum(models.Saving.amount), 0)).filter(
        models.Saving.sacco_id == sacco_id,
        models.Saving.type == 'withdraw'
    ).scalar() or 0
    
    net_savings = total_deposits - total_withdrawals
    
    # Pending deposits
    pending_deposits = db.query(models.PendingDeposit).filter(
        models.PendingDeposit.sacco_id == sacco_id,
        models.PendingDeposit.status == 'pending'
    ).count()
    
    pending_deposits_amount = db.query(func.coalesce(func.sum(models.PendingDeposit.amount), 0)).filter(
        models.PendingDeposit.sacco_id == sacco_id,
        models.PendingDeposit.status == 'pending'
    ).scalar() or 0
    
    # Loan statistics
    total_loans = db.query(func.coalesce(func.sum(models.Loan.amount), 0)).filter(
        models.Loan.sacco_id == sacco_id
    ).scalar() or 0
    
    pending_loans = db.query(models.Loan).filter(
        models.Loan.sacco_id == sacco_id,
        models.Loan.status == 'pending'
    ).count()
    
    approved_loans = db.query(models.Loan).filter(
        models.Loan.sacco_id == sacco_id,
        models.Loan.status == 'approved'
    ).count()
    
    completed_loans = db.query(models.Loan).filter(
        models.Loan.sacco_id == sacco_id,
        models.Loan.status == 'completed'
    ).count()
    
    rejected_loans = db.query(models.Loan).filter(
        models.Loan.sacco_id == sacco_id,
        models.Loan.status == 'rejected'
    ).count()
    
    # Loan payment statistics
    total_loan_payments = db.query(func.coalesce(func.sum(models.LoanPayment.amount), 0)).filter(
        models.LoanPayment.sacco_id == sacco_id
    ).scalar() or 0
    
    # Outstanding loans (principal + interest - paid)
    active_loans = db.query(models.Loan).filter(
        models.Loan.sacco_id == sacco_id,
        models.Loan.status.in_(['approved', 'partial'])
    ).all()
    
    outstanding_principal = 0
    outstanding_interest = 0
    total_outstanding = 0
    
    for loan in active_loans:
        total_paid = db.query(func.coalesce(func.sum(models.LoanPayment.amount), 0)).filter(
            models.LoanPayment.loan_id == loan.id
        ).scalar() or 0
        outstanding_principal += max(0, loan.amount - total_paid)
        total_outstanding += max(0, loan.total_payable - total_paid)
    
    # External loan statistics
    total_external_loans = db.query(func.coalesce(func.sum(models.ExternalLoan.amount), 0)).filter(
        models.ExternalLoan.sacco_id == sacco_id
    ).scalar() or 0
    
    pending_external = db.query(models.ExternalLoan).filter(
        models.ExternalLoan.sacco_id == sacco_id,
        models.ExternalLoan.status == 'pending'
    ).count()
    
    approved_external = db.query(models.ExternalLoan).filter(
        models.ExternalLoan.sacco_id == sacco_id,
        models.ExternalLoan.status == 'approved'
    ).count()
    
    # Transaction statistics (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    recent_deposits = db.query(func.coalesce(func.sum(models.Saving.amount), 0)).filter(
        models.Saving.sacco_id == sacco_id,
        models.Saving.type == 'deposit',
        models.Saving.timestamp >= thirty_days_ago,
        models.Saving.approved_by.isnot(None)
    ).scalar() or 0
    
    recent_withdrawals = db.query(func.coalesce(func.sum(models.Saving.amount), 0)).filter(
        models.Saving.sacco_id == sacco_id,
        models.Saving.type == 'withdraw',
        models.Saving.timestamp >= thirty_days_ago
    ).scalar() or 0
    
    recent_loans = db.query(func.coalesce(func.sum(models.Loan.amount), 0)).filter(
        models.Loan.sacco_id == sacco_id,
        models.Loan.timestamp >= thirty_days_ago
    ).scalar() or 0
    
    # Log statistics
    total_logs = db.query(models.Log).filter(
        models.Log.sacco_id == sacco_id
    ).count()
    
    recent_logs = db.query(models.Log).filter(
        models.Log.sacco_id == sacco_id,
        models.Log.timestamp >= thirty_days_ago
    ).count()
    
    return {
        # Member stats
        "total_members": total_members,
        "active_members": active_members,
        "inactive_members": total_members - active_members,
        
        # Staff stats
        "total_staff": total_staff,
        "managers": managers,
        "accountants": accountants,
        "credit_officers": credit_officers,
        
        # Savings stats
        "total_deposits": total_deposits,
        "total_withdrawals": total_withdrawals,
        "net_savings": net_savings,
        "pending_deposits": pending_deposits,
        "pending_deposits_amount": pending_deposits_amount,
        
        # Loan stats
        "total_loans": total_loans,
        "pending_loans": pending_loans,
        "approved_loans": approved_loans,
        "completed_loans": completed_loans,
        "rejected_loans": rejected_loans,
        "total_loan_payments": total_loan_payments,
        "outstanding_principal": outstanding_principal,
        "outstanding_total": total_outstanding,
        
        # External loan stats
        "total_external_loans": total_external_loans,
        "pending_external": pending_external,
        "approved_external": approved_external,
        
        # Recent activity (last 30 days)
        "recent_deposits": recent_deposits,
        "recent_withdrawals": recent_withdrawals,
        "recent_loans": recent_loans,
        
        # Log stats
        "total_logs": total_logs,
        "recent_logs": recent_logs,
    }


def get_member_statistics(db: Session, user_id: int) -> dict:
    """Get statistics for a specific member"""
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return {}
    
    # Savings stats
    total_deposits = db.query(func.coalesce(func.sum(models.Saving.amount), 0)).filter(
        models.Saving.user_id == user_id,
        models.Saving.type == 'deposit',
        models.Saving.approved_by.isnot(None)
    ).scalar() or 0
    
    total_withdrawals = db.query(func.coalesce(func.sum(models.Saving.amount), 0)).filter(
        models.Saving.user_id == user_id,
        models.Saving.type == 'withdraw'
    ).scalar() or 0
    
    balance = total_deposits - total_withdrawals
    
    # Loan stats
    loans = db.query(models.Loan).filter(
        models.Loan.user_id == user_id
    ).all()
    
    total_loans = sum(l.amount for l in loans)
    pending_loans = len([l for l in loans if l.status == 'pending'])
    approved_loans = len([l for l in loans if l.status == 'approved'])
    completed_loans = len([l for l in loans if l.status == 'completed'])
    
    # Calculate total paid
    total_paid = 0
    for loan in loans:
        paid = db.query(func.coalesce(func.sum(models.LoanPayment.amount), 0)).filter(
            models.LoanPayment.loan_id == loan.id
        ).scalar() or 0
        total_paid += paid
    
    # Referral stats
    total_referrals = user.total_referrals or 0
    referral_earnings = user.member_referral_earnings or 0
    
    return {
        "balance": balance,
        "total_deposits": total_deposits,
        "total_withdrawals": total_withdrawals,
        "total_loans": total_loans,
        "total_paid": total_paid,
        "pending_loans": pending_loans,
        "approved_loans": approved_loans,
        "completed_loans": completed_loans,
        "total_referrals": total_referrals,
        "referral_earnings": referral_earnings,
    }