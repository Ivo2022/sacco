from .database import SessionLocal
from . import models
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional, cast
from datetime import datetime

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return pwd_context.hash(password)
	

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

"""
def create_user(db: Session, *, full_name: Optional[str], email: str, password: str, role: models.RoleEnum = models.RoleEnum.MEMBER, sacco_id: Optional[int] = None, username: str, **kwargs):
    # Create a new user. Raises ValueError on duplicate email or other integrity issues.

    # Returns the created user on success.
    
    hashed = get_password_hash(password)
    user = models.User(full_name=full_name, email=email, password_hash=hashed, role=role, sacco_id=sacco_id, username=username)
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError:
        db.rollback()
        raise ValueError("A user with that email already exists")
"""

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
):
    """Create a new user with proper role settings"""
    
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    # Check if email already exists
    existing_user = db.query(models.User).filter(models.User.email == email).first()
    if existing_user:
        raise ValueError(f"models.User with email {email} already exists")
    
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
    hashed_password = pwd_context.hash(password)
    
    # Set role-specific permissions
    if role == models.RoleEnum.SACCO_ADMIN:
        is_staff = True
        can_apply_for_loans = False  # Admins cannot apply for loans using admin account
        can_receive_dividends = False  # Admins don't receive dividends
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


def authenticate_user(db: Session, email: str, password: str):
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        return None
    # cast the ORM column value to str for static type checkers (at runtime this is a string)
    hashed = cast(str, user.password_hash)
    if not verify_password(password, hashed):
        return None
    return user


def create_sacco(db: Session, name: str, email: Optional[str] = None):
    sacco = models.Sacco(name=name, email=email)
    db.add(sacco)
    db.commit()
    db.refresh(sacco)
    return sacco

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
    existing = db.query( models.Sacco).filter( models.Sacco.name == name).first()
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

def get_sacco(db: Session, sacco_id: int):
    return db.query(models.Sacco).filter(models.Sacco.id == sacco_id).first()


def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()
	
# backend/services.py
"""
def create_log(
    db: Session, 
    action: str, 
    user_id: int = None, 
    sacco_id: int = None, 
    details: str = None,
    ip_address: str = None
):
    Create a log entry for audit purposes
    try:
        from .models import Log
        
        log = Log(
            action=action,
            user_id=user_id,
            sacco_id=sacco_id,
            details=details,
            ip_address=ip_address
        )
        db.add(log)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Failed to create log: {e}")
"""
# backend/services.py

def create_admin_with_member_account(
    db: Session,
    admin_email: str,
    admin_password: str,
    admin_full_name: str,
    sacco_id: int,
    member_username: str = None,
    member_email: str = None
):
    """Create an admin account and a linked member account for the same person"""
    
    # Create admin account
    admin = create_user(
        db,
        email=admin_email,
        password=admin_password,
        role=models.RoleEnum.SACCO_ADMIN,
        sacco_id=sacco_id,
        full_name=admin_full_name,
        is_staff=True,
        can_apply_for_loans=False,
        can_receive_dividends=False
    )
    
    # Create member email (if not provided)
    if not member_email:
        member_email = f"{admin_email.split('@')[0]}_member@{admin_email.split('@')[1]}"
    
    # Create member account
    member = create_user(
        db,
        email=member_email,
        password=admin_password,
        role=models.RoleEnum.MEMBER,
        sacco_id=sacco_id,
        full_name=f"{admin_full_name} (Member Account)",
        username=member_username or f"{admin.username}_member",
        is_staff=True,
        can_apply_for_loans=True,
        can_receive_dividends=True,
        requires_approval_for_loans=True
    )
    
    # Link accounts using simple ID references
    admin.linked_member_account_id = member.id
    member.linked_admin_id = admin.id
    
    db.commit()
    db.refresh(admin)
    db.refresh(member)
    
    return {
        "admin": admin,
        "member": member,
        "admin_credentials": {
            "email": admin_email,
            "password": admin_password,
            "role": "SACCO_ADMIN"
        },
        "member_credentials": {
            "email": member_email,
            "password": admin_password,
            "role": "MEMBER"
        }
    }

def get_linked_member_account(db: Session, admin_user: models.User):
    """Get the linked member account for an admin"""
    if admin_user.linked_member_account_id:
        return db.query(User).filter(User.id == admin_user.linked_member_account_id).first()
    return None

