# backend/routers/insights.py
"""
Smart Insights Router
Provides endpoints for insights dashboard and alerts
"""
from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from datetime import datetime, timedelta
import logging

# Fix imports - adjust based on your actual file locations
from ..core import get_db, get_current_user, require_role  # Try this first
# OR
# from ..core.dependencies import get_db, get_current_user, require_role  # Alternative

from ..core.context import get_template_context
from ..models import User, RoleEnum
from ..models.insights import InsightLog, AlertRule
from ..models import Loan  # Add this
from ..models import Saving  # Add this
from ..services.insights_service import InsightsService
from ..utils.helpers import get_template_helpers
from ..utils import create_log

router = APIRouter()
logger = logging.getLogger(__name__)


def serialize_insight(insight: InsightLog) -> dict:
    """Serialize InsightLog for JSON response"""
    return {
        "id": insight.id,
        "type": insight.insight_type,
        "title": insight.title,
        "description": insight.description,
        "data": insight.data,
        "severity": insight.severity,
        "is_resolved": insight.is_resolved,
        "generated_at": insight.generated_at.isoformat() if insight.generated_at else None,
        "resolved_at": insight.resolved_at.isoformat() if insight.resolved_at else None
    }


@router.get("/manager/insights/dashboard")
async def insights_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([RoleEnum.SUPER_ADMIN, RoleEnum.MANAGER]))
):
    """Render insights dashboard"""
    templates = request.app.state.templates
    insights_service = InsightsService(db, user.sacco_id)
    
    # Get active alerts
    active_alerts = insights_service.get_active_alerts()
    
    helpers = get_template_helpers()
    base_context = get_template_context(request, user)
    context = {
        **base_context,
        "active_alerts": [serialize_insight(a) for a in active_alerts],
        "alert_count": len(active_alerts),
        **helpers
    }
    return templates.TemplateResponse("admin/insights_dashboard.html", context)


@router.get("/api/insights/alerts")
async def get_alerts(
    resolved: bool = Query(False),
    limit: int = Query(50),
    db: Session = Depends(get_db),
    user: User = Depends(require_role([RoleEnum.SUPER_ADMIN, RoleEnum.MANAGER]))
):
    """API endpoint to get alerts"""
    query = db.query(InsightLog).filter(
        InsightLog.sacco_id == user.sacco_id,
        InsightLog.is_resolved == resolved
    ).order_by(InsightLog.generated_at.desc())
    
    alerts = query.limit(limit).all()
    return {
        "success": True,
        "alerts": [serialize_insight(a) for a in alerts],
        "count": len(alerts)
    }


@router.post("/api/insights/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([RoleEnum.SUPER_ADMIN, RoleEnum.MANAGER]))
):
    """Resolve an alert"""
    insights_service = InsightsService(db, user.sacco_id)
    success = insights_service.resolve_alert(alert_id, user.id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    create_log(
        db,
        action="ALERT_RESOLVED",
        user_id=user.id,
        sacco_id=user.sacco_id,
        details=f"Alert #{alert_id} resolved by {user.email}"
    )
    
    return {"success": True, "message": "Alert resolved successfully"}


@router.post("/api/insights/generate")
async def generate_insights(
    db: Session = Depends(get_db),
    user: User = Depends(require_role([RoleEnum.SUPER_ADMIN, RoleEnum.MANAGER]))
):
    """Manually trigger insight generation"""
    insights_service = InsightsService(db, user.sacco_id)
    insights = insights_service.generate_all_insights()
    
    create_log(
        db,
        action="INSIGHTS_GENERATED",
        user_id=user.id,
        sacco_id=user.sacco_id,
        details=f"Generated {len(insights)} insights"
    )
    
    return {
        "success": True,
        "insights_generated": len(insights),
        "insights": insights
    }


@router.get("/api/insights/weekly-summary")
async def get_weekly_summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_role([RoleEnum.SUPER_ADMIN, RoleEnum.MANAGER]))
):
    """Get weekly summary data for insights dashboard."""
    sacco_id = user.sacco_id
    
    # Calculate week start and end
    today = datetime.utcnow().date()
    week_start = today - timedelta(days=today.weekday())  # Monday
    week_end = week_start + timedelta(days=6)  # Sunday
    
    # Get weekly metrics
    week_start_datetime = datetime(week_start.year, week_start.month, week_start.day, 0, 0, 0)
    week_end_datetime = datetime(week_end.year, week_end.month, week_end.day, 23, 59, 59)
    
    # New members this week
    new_members = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER,
        User.created_at >= week_start_datetime,
        User.created_at <= week_end_datetime
    ).count()
    
    # New loans this week
    new_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.timestamp >= week_start_datetime,
        Loan.timestamp <= week_end_datetime
    ).count()
    
    # New savings this week
    total_new_savings = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == sacco_id,
        Saving.type == 'deposit',
        Saving.timestamp >= week_start_datetime,
        Saving.timestamp <= week_end_datetime
    ).scalar() or 0
    
    # Loans disbursed this week
    total_loans_amount = db.query(func.sum(Loan.amount)).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == 'approved',
        Loan.timestamp >= week_start_datetime,
        Loan.timestamp <= week_end_datetime
    ).scalar() or 0
    
    # Generate top insights based on data
    top_insights = []
    
    if new_members > 10:
        top_insights.append({
            "title": "Strong Member Growth",
            "description": f"{new_members} new members joined this week.",
            "severity": "info"
        })
    elif new_members > 5:
        top_insights.append({
            "title": "Steady Member Growth",
            "description": f"{new_members} new members joined this week.",
            "severity": "info"
        })
    
    if new_loans > 20:
        top_insights.append({
            "title": "High Loan Demand",
            "description": f"{new_loans} loan applications received this week.",
            "severity": "warning"
        })
    elif new_loans > 10:
        top_insights.append({
            "title": "Increased Loan Activity",
            "description": f"{new_loans} loan applications this week.",
            "severity": "info"
        })
    
    if total_new_savings > 10000000:
        top_insights.append({
            "title": "Strong Savings Growth",
            "description": f"UGX {total_new_savings:,.0f} in new savings this week.",
            "severity": "success"
        })
    
    weekly_summary_data = {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "metrics": {
            "new_members": new_members,
            "new_loans": new_loans,
            "total_new_savings": float(total_new_savings),
            "total_loans_amount": float(total_loans_amount)
        },
        "top_insights": top_insights
    }
    
    return {
        "success": True,
        "summary": weekly_summary_data
    }


@router.get("/api/insights/inactive-members")
async def get_inactive_members(
    days: int = Query(30),
    db: Session = Depends(get_db),
    user: User = Depends(require_role([RoleEnum.SUPER_ADMIN, RoleEnum.MANAGER]))
):
    """Get list of inactive members"""
    insights_service = InsightsService(db, user.sacco_id)
    inactive = insights_service.detect_inactive_savers(days)
    
    return {
        "success": True,
        "inactive_members": inactive[0].get("data", []) if inactive else [],
        "count": len(inactive[0].get("data", [])) if inactive else 0
    }


@router.get("/api/insights/risk-analysis")
async def get_risk_analysis(
    db: Session = Depends(get_db),
    user: User = Depends(require_role([RoleEnum.SUPER_ADMIN, RoleEnum.MANAGER, RoleEnum.CREDIT_OFFICER]))
):
    """Get loan risk analysis"""
    insights_service = InsightsService(db, user.sacco_id)
    defaulters = insights_service.detect_likely_defaulters()
    
    return {
        "success": True,
        "high_risk_loans": defaulters[0].get("data", []) if defaulters else [],
        "count": len(defaulters[0].get("data", [])) if defaulters else 0
    }