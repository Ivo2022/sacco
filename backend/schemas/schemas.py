# backend/schemas/schemas.py
from enum import Enum
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional
from datetime import datetime

class RoleEnum(str, Enum):
    MANAGER = "MANAGER"
    ACCOUNTANT = "ACCOUNTANT"
    CREDIT_OFFICER = "CREDIT_OFFICER"
    MEMBER = "MEMBER"
    
    # If you need to keep these for backward compatibility
    SUPER_ADMIN = "SUPER_ADMIN"
    # LEGACY: SACCO_ADMIN = "sacco_admin"  # Mark as legacy if needed

class PaymentMethodEnum(str, Enum):
    CASH = "CASH"
    BANK_TRANSFER = "BANK_TRANSFER"
    MOBILE_MONEY = "MOBILE_MONEY"
    SAVINGS = "SAVINGS"
    CHEQUE = "CHEQUE"

# ============ Sacco Schemas ============
class SaccoBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = None
    registration_no: Optional[str] = None
    website: Optional[str] = None
    
class SaccoCreate(SaccoBase):
    referred_by_code: Optional[str] = Field(None, description="Referral code from referrer")
    
class SaccoUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    website: Optional[str] = None
    status: Optional[str] = None

class SaccoOut(SaccoBase):
    id: int
    status: str = "active"
    created_at: datetime
    referral_commission_paid: float = 0.0
    
    model_config = ConfigDict(from_attributes=True)

# ============ User Schemas ============
class UserBase(BaseModel):
    email: EmailStr
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    role: RoleEnum = RoleEnum.MEMBER
    
class UserCreate(UserBase):
    password: str = Field(..., min_length=6)
    sacco_id: Optional[int] = None
    referral_code: Optional[str] = Field(None, description="Referral code if referred by someone")
    
class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    profile_picture: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    national_id: Optional[str] = None
    is_active: Optional[bool] = None
    role: Optional[RoleEnum] = None

class UserOut(UserBase):
    id: int
    sacco_id: Optional[int]
    is_active: bool
    is_staff: bool = False
    created_at: datetime
    profile_picture: Optional[str] = None
    
    # Optional fields for detailed views
    national_id: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    address: Optional[str] = None
    
    # Referral fields
    referral_code: Optional[str] = None
    total_referrals: int = 0
    member_referral_earnings: float = 0.0
    
    model_config = ConfigDict(from_attributes=True)

class UserResponse(UserOut):
    """Alias for UserOut for backward compatibility"""
    pass

# ============ Loan Schemas ============
class LoanBase(BaseModel):
    amount: float = Field(..., gt=0)
    term: int = Field(..., gt=0, description="Term in months")
    interest_rate: float = Field(12.0, ge=0, le=100)
    purpose: Optional[str] = Field(None, max_length=200)

class LoanCreate(LoanBase):
    sacco_id: int
    
class LoanOut(LoanBase):
    id: int
    sacco_id: int
    user_id: int
    status: str
    timestamp: datetime
    total_interest: float
    total_payable: float
    total_paid: float
    approved_by: Optional[int]
    approved_at: Optional[datetime]
    approval_notes: Optional[str]
    
    model_config = ConfigDict(from_attributes=True)

# ============ Saving Schemas ============
class SavingBase(BaseModel):
    amount: float = Field(..., gt=0)
    payment_method: PaymentMethodEnum = PaymentMethodEnum.CASH
    description: Optional[str] = Field(None, max_length=200)
    reference_number: Optional[str] = Field(None, max_length=100)

class SavingCreate(SavingBase):
    sacco_id: int
    
class SavingOut(SavingBase):
    id: int
    sacco_id: int
    user_id: int
    type: str
    timestamp: datetime
    approved_by: Optional[int]
    approved_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)

# ============ Pending Deposit Schemas ============
class PendingDepositBase(BaseModel):
    amount: float = Field(..., gt=0)
    payment_method: Optional[str] = None
    description: Optional[str] = None
    reference_number: Optional[str] = None

class PendingDepositCreate(PendingDepositBase):
    sacco_id: int
    
class PendingDepositOut(PendingDepositBase):
    id: int
    sacco_id: int
    user_id: int
    status: str
    timestamp: datetime
    approved_by: Optional[int]
    approved_at: Optional[datetime]
    rejection_reason: Optional[str]
    
    model_config = ConfigDict(from_attributes=True)

# ============ External Loan Schemas ============
class ExternalLoanBase(BaseModel):
    amount: float = Field(..., gt=0)
    term: int = Field(..., gt=0)
    interest_rate: float = Field(15.0, ge=0, le=100)
    purpose: Optional[str] = None
    collateral_description: str = Field(..., min_length=10)
    collateral_value: float = Field(..., gt=0)
    borrower_name: str = Field(..., min_length=2)
    borrower_contact: str = Field(..., min_length=10)
    borrower_national_id: str = Field(..., min_length=5)

class ExternalLoanCreate(ExternalLoanBase):
    sacco_id: int
    guarantor_id: int
    
class ExternalLoanOut(ExternalLoanBase):
    id: int
    sacco_id: int
    guarantor_id: int
    status: str
    timestamp: datetime
    total_interest: float
    total_payable: float
    total_paid: float
    approved_by: Optional[int]
    approved_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)

# ============ Auth Schemas ============
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)

# ============ Referral Schemas ============
class ReferralRequest(BaseModel):
    referral_code: str
    entity_type: str  # 'sacco', 'member', 'agent'

class ReferralCommissionOut(BaseModel):
    id: int
    referrer_id: int
    referred_entity_type: str
    referral_type: str
    amount: float
    percentage: float
    status: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# ============ Common Response Schemas ============
class MessageResponse(BaseModel):
    message: str
    success: bool = True

class ErrorResponse(BaseModel):
    detail: str
    success: bool = False