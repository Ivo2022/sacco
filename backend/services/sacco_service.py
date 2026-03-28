# backend/services/sacco_service.py
"""
SACCO-related service functions
"""

from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from .. import models


def create_sacco(
    db: Session, 
    name: str, 
    email: str = None, 
    phone: str = None, 
    address: str = None,
    registration_no: str = None,
    website: str = None
) -> models.Sacco:
    """Create a new SACCO"""
    
    # Check if SACCO with this name already exists
    existing = db.query(models.Sacco).filter(models.Sacco.name == name).first()
    if existing:
        raise ValueError(f"SACCO with name '{name}' already exists")
    
    # Create new SACCO
    sacco = models.Sacco(
        name=name,
        email=email,
        phone=phone,
        address=address,
        registration_no=registration_no,
        website=website,
        status='active',
        created_at=datetime.utcnow()
    )
    
    db.add(sacco)
    db.commit()
    db.refresh(sacco)
    
    return sacco


def get_sacco(db: Session, sacco_id: int) -> Optional[models.Sacco]:
    """Get a SACCO by ID"""
    return db.query(models.Sacco).filter(models.Sacco.id == sacco_id).first()


def get_all_saccos(db: Session) -> list:
    """Get all active SACCOs"""
    return db.query(models.Sacco).filter(models.Sacco.status == 'active').order_by(models.Sacco.name).all()