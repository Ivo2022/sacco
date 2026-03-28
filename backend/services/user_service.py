# backend/services/user_service.py
"""
User-related service functions
"""

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from passlib.context import CryptContext
from typing import Optional, cast
from datetime import datetime
from .. import models

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt"""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain, hashed)


def create_user(
    db: Session, 
    email: str, 
    password: str, 
    role: models.RoleEnum, 
    sacco_id: int = None, 
    full_name: str = None,
    username: str = None,
    is_staff: bool = False,
    can_apply_for_loans: bool = True,
    can_receive_dividends: bool = True,
    requires_approval_for_loans: bool = False,
    **kwargs
) -> models.User:
    """Create a new user with proper role settings"""
    
    # Check if email already exists
    existing_user = db.query(models.User).filter(models.User.email == email).first()
    if existing_user:
        raise ValueError(f"User with email {email} already exists")
    
    # Generate username if not provided
    if not username:
        if full_name:
            username = full_name.lower().replace(' ', '.')
            username = ''.join(c for c in username if c.isalnum() or c == '.')
        else:
            username = email.split('@')[0]
        
        # Make sure username is unique
        base_username = username
        counter = 1
        while db.query(models.User).filter(models.User.username == username).first():
            username = f"{base_username}{counter}"
            counter += 1
    
    # Check if username already exists
    existing_username = db.query(models.User).filter(models.User.username == username).first()
    if existing_username:
        raise ValueError(f"Username '{username}' is already taken. Please choose another one.")
    
    # Hash password
    hashed_password = get_password_hash(password)
    
    # Set role-specific permissions
    if role == models.RoleEnum.SACCO_ADMIN:
        is_staff = True
        can_apply_for_loans = False
        can_receive_dividends = False
        requires_approval_for_loans = False
        
    elif role == models.RoleEnum.SUPER_ADMIN:
        is_staff = True
        can_apply_for_loans = False
        can_receive_dividends = False
        requires_approval_for_loans = False
    
    # Create user
    db_user = models.User(
        email=email,
        password_hash=hashed_password,
        role=role,
        sacco_id=sacco_id,
        full_name=full_name,
        username=username,
        is_staff=is_staff,
        can_apply_for_loans=can_apply_for_loans,
        can_receive_dividends=can_receive_dividends,
        requires_approval_for_loans=requires_approval_for_loans,
        **kwargs
    )
    
    try:
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    except IntegrityError as e:
        db.rollback()
        if "email" in str(e):
            raise ValueError(f"Email {email} is already registered")
        elif "username" in str(e):
            raise ValueError(f"Username '{username}' is already taken")
        else:
            raise ValueError(f"Database error: {str(e)}")


def authenticate_user(db: Session, email: str, password: str) -> Optional[models.User]:
    """Authenticate a user by email and password"""
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        return None
    hashed = cast(str, user.password_hash)
    if not verify_password(password, hashed):
        return None
    return user


def get_user(db: Session, user_id: int) -> Optional[models.User]:
    """Get a user by ID"""
    return db.query(models.User).filter(models.User.id == user_id).first()