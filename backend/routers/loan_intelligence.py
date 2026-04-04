# backend/routers/loan_intelligence.py
"""
Loan Intelligence Router
Provides endpoints for loan risk scoring and eligibility
"""
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
import logging

from ..core.dependencies import get_db, get_current_user, require_role
from ..models import User, RoleEnum, Loan
from ..services.loan_intelligence import LoanIntelligenceService
from ..utils.helpers import get_template_helpers
from ..utils import create_log

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/api/loan/eligibility")
async def check_loan_eligibility(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Check loan eligibility for current user"""
    service = LoanIntelligenceService(db)
    eligibility = service.calculate_eligibility_score(user.id)
    
    return {
        "success": True,
        "eligibility": eligibility
    }


@router.get("/api/loan/{loan_id}/risk")
async def get_loan_risk(
    loan_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([RoleEnum.MANAGER, RoleEnum.CREDIT_OFFICER, RoleEnum.SUPER_ADMIN]))
):
    """Get risk assessment for a specific loan"""
    service = LoanIntelligenceService(db)
    risk = service.calculate_risk_score(loan_id)
    
    return {
        "success": True,
        "risk_assessment": risk
    }


@router.post("/api/loan/{loan_id}/generate-schedule")
async def generate_repayment_schedule(
    loan_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([RoleEnum.MANAGER, RoleEnum.CREDIT_OFFICER, RoleEnum.SUPER_ADMIN]))
):
    """Generate repayment schedule for a loan"""
    service = LoanIntelligenceService(db)
    schedule = service.generate_repayment_schedule(loan_id)
    
    create_log(
        db,
        action="REPAYMENT_SCHEDULE_GENERATED",
        user_id=user.id,
        sacco_id=user.sacco_id,
        details=f"Repayment schedule generated for loan #{loan_id}"
    )
    
    return {
        "success": True,
        "schedule": schedule
    }


@router.get("/api/loan/early-warnings")
async def get_early_warnings(
    db: Session = Depends(get_db),
    user: User = Depends(require_role([RoleEnum.MANAGER, RoleEnum.CREDIT_OFFICER, RoleEnum.SUPER_ADMIN]))
):
    """Get loans with early warning signs"""
    service = LoanIntelligenceService(db)
    warnings = service.get_early_warnings(user.sacco_id)
    
    return {
        "success": True,
        "warnings": warnings,
        "count": len(warnings)
    }


@router.get("/api/loan/portfolio-risk")
async def get_portfolio_risk(
    db: Session = Depends(get_db),
    user: User = Depends(require_role([RoleEnum.MANAGER, RoleEnum.SUPER_ADMIN]))
):
    """Get loan portfolio risk summary"""
    service = LoanIntelligenceService(db)
    summary = service.get_loan_portfolio_risk_summary(user.sacco_id)
    
    return {
        "success": True,
        "portfolio_risk": summary
    }


@router.get("/manager/loan-risk-dashboard")
async def loan_risk_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([RoleEnum.MANAGER, RoleEnum.CREDIT_OFFICER, RoleEnum.SUPER_ADMIN]))
):
    """Render loan risk dashboard"""
    templates = request.app.state.templates
    service = LoanIntelligenceService(db)
    
    warnings = service.get_early_warnings(user.sacco_id)
    portfolio_risk = service.get_loan_portfolio_risk_summary(user.sacco_id)
    
    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": user,
        "warnings": warnings,
        "portfolio_risk": portfolio_risk,
        **helpers
    }
    return templates.TemplateResponse("manager/loan_risk_dashboard.html", context)