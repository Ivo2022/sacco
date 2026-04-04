# backend/services/dividend_service.py
"""
Dividend Service Layer
Handles business logic for dividend declarations and payments
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
import logging

from ..models import User
from ..models.share import Share, DividendDeclaration, DividendPayment, ShareTransaction, ShareTransactionType
from ..services.share_service import get_member_share_holdings

logger = logging.getLogger(__name__)


def declare_dividend(
    db: Session,
    sacco_id: int,
    fiscal_year: int,
    rate: float,
    declared_by: int,
    share_type_id: int = None
) -> DividendDeclaration:
    """Declare a dividend for a fiscal year"""
    # Calculate total dividend pool
    query = db.query(Share).filter(Share.sacco_id == sacco_id)
    
    if share_type_id:
        query = query.filter(Share.share_type_id == share_type_id)
    
    shares = query.all()
    total_value = sum(share.total_value for share in shares)
    total_dividend_pool = total_value * (rate / 100)
    
    # Create declaration
    declaration = DividendDeclaration(
        sacco_id=sacco_id,
        share_type_id=share_type_id,
        fiscal_year=fiscal_year,
        rate=rate,
        amount_per_share=0,  # Will be calculated per share type
        total_dividend_pool=total_dividend_pool,
        declared_by=declared_by,
        status="pending"
    )
    
    db.add(declaration)
    db.commit()
    db.refresh(declaration)
    
    return declaration


def calculate_dividend_for_member(db: Session, user_id: int, fiscal_year: int) -> dict:
    """Calculate dividend entitlement for a specific member"""
    holdings = get_member_share_holdings(db, user_id)
    
    # Find dividend declarations for the fiscal year
    declarations = db.query(DividendDeclaration).filter(
        DividendDeclaration.fiscal_year == fiscal_year,
        DividendDeclaration.status == "pending"
    ).all()
    
    total_dividend = 0
    breakdown = []
    
    for holding in holdings:
        for declaration in declarations:
            if declaration.share_type_id and declaration.share_type_id != holding["share_type_id"]:
                continue
            
            dividend = holding["total_value"] * (declaration.rate / 100)
            total_dividend += dividend
            
            breakdown.append({
                "declaration_id": declaration.id,
                "share_type": holding["share_type_name"],
                "value": holding["total_value"],
                "rate": declaration.rate,
                "dividend": dividend
            })
    
    return {
        "total_dividend": total_dividend,
        "breakdown": breakdown,
        "fiscal_year": fiscal_year,
        "has_declaration": len(declarations) > 0
    }


def pay_dividends(
    db: Session,
    declaration_id: int,
    payment_method: str = "bank_transfer"
) -> list:
    """Process dividend payments for a declaration"""
    declaration = db.query(DividendDeclaration).filter(
        DividendDeclaration.id == declaration_id
    ).first()
    
    if not declaration:
        raise ValueError("Declaration not found")
    
    if declaration.status != "pending":
        raise ValueError("Dividends already processed")
    
    # Get all share holdings for this SACCO
    query = db.query(Share).filter(Share.sacco_id == declaration.sacco_id)
    
    if declaration.share_type_id:
        query = query.filter(Share.share_type_id == declaration.share_type_id)
    
    shares = query.all()
    payments = []
    
    for share in shares:
        dividend_amount = share.total_value * (declaration.rate / 100)
        
        if dividend_amount > 0:
            # Check if already paid
            existing = db.query(DividendPayment).filter(
                DividendPayment.declaration_id == declaration_id,
                DividendPayment.user_id == share.user_id,
                DividendPayment.share_id == share.id
            ).first()
            
            if existing:
                continue
            
            payment = DividendPayment(
                declaration_id=declaration_id,
                user_id=share.user_id,
                sacco_id=declaration.sacco_id,
                share_id=share.id,
                shares_held=share.quantity,
                amount=dividend_amount,
                payment_method=payment_method,
                paid_at=datetime.utcnow()
            )
            db.add(payment)
            payments.append(payment)
    
    # Update declaration status
    declaration.status = "paid"
    declaration.payment_date = datetime.utcnow()
    
    db.commit()
    
    return payments


def get_dividend_history(db: Session, sacco_id: int, limit: int = 50):
    """Get dividend declaration history"""
    return db.query(DividendDeclaration).filter(
        DividendDeclaration.sacco_id == sacco_id
    ).order_by(DividendDeclaration.declared_date.desc()).limit(limit).all()