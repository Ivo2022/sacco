# backend/models.py

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float, Enum, Boolean, Text
from sqlalchemy.orm import relationship, Mapped, mapped_column
from ..core.database import Base
import datetime
import enum
# Import from schemas package
from ..schemas import RoleEnum, PaymentMethodEnum


class RoleEnum(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    SACCO_ADMIN = "SACCO_ADMIN" # Legacy to be replaced
    MEMBER = "MEMBER"
	
    # New specialized roles
    MANAGER = "MANAGER"           # Overall SACCO manager - can approve loans
    ACCOUNTANT = "ACCOUNTANT"     # Handles finances - approves deposits/withdrawals
    CREDIT_OFFICER = "CREDIT_OFFICER"  # Follows up on loans - sends reminders
    
    # Optional additional roles
    TELLER = "TELLER"             # Processes daily transactions
    LOAN_OFFICER = "LOAN_OFFICER" # Processes loan applications
	

class PaymentMethodEnum(str, enum.Enum):
    CASH = "CASH"
    BANK_TRANSFER = "BANK_TRANSFER"
    MOBILE_MONEY = "MOBILE_MONEY"
    SAVINGS = "SAVINGS"
    CHEQUE = "CHEQUE"


class Sacco(Base):
    __tablename__ = "saccos"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, nullable=True)
    phone = Column(String)
    address = Column(String)
    registration_no = Column(String)
    website = Column(String)
    status = Column(String, default='active')
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
	
    # Referral fields
    referred_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    referral_commission_paid = Column(Float, default=0.0)

    # Relationships
    users = relationship("User", foreign_keys="[User.sacco_id]", back_populates="sacco", cascade="all, delete")
    savings = relationship("Saving", foreign_keys="[Saving.sacco_id]", back_populates="sacco", cascade="all, delete")
    loans = relationship("Loan", foreign_keys="[Loan.sacco_id]", back_populates="sacco", cascade="all, delete")
    loan_payments = relationship("LoanPayment", foreign_keys="[LoanPayment.sacco_id]", back_populates="sacco", cascade="all, delete")
    logs = relationship("Log", foreign_keys="[Log.sacco_id]", back_populates="sacco", cascade="all, delete")
    external_loans = relationship("ExternalLoan", foreign_keys="[ExternalLoan.sacco_id]", back_populates="sacco", cascade="all, delete")
    pending_deposits = relationship("PendingDeposit", foreign_keys="[PendingDeposit.sacco_id]", back_populates="sacco", cascade="all, delete")
    # Referrer relationship
    referrer = relationship("User", foreign_keys=[referred_by_id], overlaps="referred_by")
    referred_by = relationship("User", foreign_keys=[referred_by_id], back_populates=None, overlaps="referrer,referred_saccos")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=True)
    username = Column(String, unique=True, nullable=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum), default=RoleEnum.MEMBER)
    sacco_id = Column(Integer, ForeignKey("saccos.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    is_active = Column(Boolean, default=True)
    password_reset_required = Column(Boolean, default=False)
    
    # Additional fields
    profile_picture = Column(String, nullable=True)
    date_of_birth = Column(DateTime, nullable=True)
    national_id = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(String, nullable=True)
    
    # Staff/Admin management fields
    is_staff = Column(Boolean, default=False)
    can_apply_for_loans = Column(Boolean, default=True)
    can_receive_dividends = Column(Boolean, default=True)
    requires_approval_for_loans = Column(Boolean, default=False)
    
    # Simple link - just store the ID, no relationship
    linked_member_account_id = Column(Integer, nullable=True)
    linked_admin_id = Column(Integer, nullable=True)
	
	# Referral fields
    referred_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    referral_code = Column(String(20), unique=True, nullable=True, index=True)
    total_referrals = Column(Integer, default=0)
    
    # SACCO-Level Referrals
    referred_saccos = relationship("Sacco", foreign_keys="Sacco.referred_by_id", back_populates="referrer", overlaps="referred_by")
    sacco_referral_code = Column(String(20), unique=True, nullable=True)
    sacco_referral_earnings = Column(Float, default=0.0)
    sacco_referral_commission_rate = Column(Float, default=15.0)  # 15% for SACCO referrals
    
    # Member-Level Referrals
    referred_members = relationship("User", foreign_keys="User.referred_by_id", remote_side=[id], overlaps="referred_by")
    member_referral_code = Column(String(20), unique=True, nullable=True)
    member_referral_earnings = Column(Float, default=0.0)
    member_referral_commission_rate = Column(Float, default=3.0)  # 3% for member referrals
    
    # Agent flag (for marketing team)
    is_agent = Column(Boolean, default=False)
    agent_referral_code = Column(String(20), unique=True, nullable=True)
    
    # Add approval tracking
    is_approved = Column(Boolean, default=False)  # For self-registered members
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    rejection_reason = Column(String(500), nullable=True)
    
    # Relationships for approval
    approver = relationship("User", foreign_keys=[approved_by], remote_side=[id])

    # Relationships
    referred_by = relationship("User", foreign_keys=[referred_by_id], remote_side=[id], overlaps="referred_members")
    referred_members = relationship("User", foreign_keys=[referred_by_id], remote_side=[id], back_populates="referred_by", overlaps="referred_by")
	
    # Relationships - Simplified, no complex backrefs
    sacco = relationship("Sacco", foreign_keys=[sacco_id], back_populates="users")
    
    # Simple one-way relationships (no back_populates where not needed)
    savings = relationship("Saving", foreign_keys="[Saving.user_id]", cascade="all, delete", overlaps="user")
    loans = relationship("Loan", foreign_keys="[Loan.user_id]", cascade="all, delete", overlaps="user")
    approved_loans = relationship("Loan", foreign_keys="[Loan.approved_by]", overlaps="approver")
    loan_payments = relationship("LoanPayment", foreign_keys="[LoanPayment.user_id]", cascade="all, delete", overlaps="user")
    logs = relationship("Log", foreign_keys="[Log.user_id]", cascade="all, delete", overlaps="user")
    pending_deposits = relationship("PendingDeposit", foreign_keys="[PendingDeposit.user_id]", cascade="all, delete", overlaps="user")
    approved_deposits = relationship("PendingDeposit", foreign_keys="[PendingDeposit.approved_by]", overlaps="approver")
    
    # External loans where this user is guarantor
    guaranteed_external_loans = relationship("ExternalLoan", foreign_keys="[ExternalLoan.guarantor_id]", overlaps="guarantor")
    recorded_external_loan_payments = relationship("ExternalLoanPayment", foreign_keys="[ExternalLoanPayment.recorded_by]", overlaps="recorder")
	
    # Role-specific permissions (calculated based on role)
    can_apply_for_loans = Column(Boolean, default=True)  # This should exist
	
    @property
    def can_approve_loans(self) -> bool:
        """Check if user can approve loans"""
        return self.role in [RoleEnum.MANAGER, RoleEnum.LOAN_OFFICER, RoleEnum.SUPER_ADMIN]
    
    @property
    def can_approve_deposits(self) -> bool:
        """Check if user can approve deposits"""
        return self.role in [RoleEnum.ACCOUNTANT, RoleEnum.MANAGER, RoleEnum.SUPER_ADMIN]
    
    @property
    def can_manage_loans(self) -> bool:
        """Check if user can manage loans (approve, reject, modify)"""
        return self.role in [RoleEnum.MANAGER, RoleEnum.CREDIT_OFFICER, RoleEnum.LOAN_OFFICER, RoleEnum.SUPER_ADMIN]
    
    @property
    def can_send_loan_reminders(self) -> bool:
        """Check if user can send loan reminders"""
        return self.role in [RoleEnum.CREDIT_OFFICER, RoleEnum.MANAGER, RoleEnum.SUPER_ADMIN]
    
    @property
    def can_view_all_transactions(self) -> bool:
        """Check if user can view all transactions"""
        return self.role in [RoleEnum.ACCOUNTANT, RoleEnum.MANAGER, RoleEnum.SUPER_ADMIN]
    
    @property
    def get_dashboard_url(self) -> str:
        """Get the appropriate dashboard URL based on role"""
        if self.role == RoleEnum.SUPER_ADMIN:
            return "/superadmin/dashboard"
        elif self.role == RoleEnum.MANAGER:
            return "/manager/dashboard"
        elif self.role == RoleEnum.ACCOUNTANT:
            return "/accountant/dashboard"
        elif self.role == RoleEnum.CREDIT_OFFICER:
            return "/credit-officer/dashboard"
        elif self.role == RoleEnum.MEMBER:
            return "/member/dashboard"
        else:
            return "/sacco/dashboard"  # Fallback

    @property
    def linked_member_account(self):
        """Get the linked member account for this admin"""
        if self.linked_member_account_id:
            from .database import SessionLocal
            db = SessionLocal()
            try:
                return db.query(User).filter(User.id == self.linked_member_account_id).first()
            finally:
                db.close()
        return None
    
    @property
    def linked_admin_account(self):
        """Get the linked admin account for this member"""
        if self.linked_admin_id:
            from .database import SessionLocal
            db = SessionLocal()
            try:
                return db.query(User).filter(User.id == self.linked_admin_id).first()
            finally:
                db.close()
        return None
		
    @property
    def is_admin(self) -> bool:
        """Check if user is an admin"""
        return self.role in [RoleEnum.SUPER_ADMIN, RoleEnum.MANAGER, 
                            RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER]

class PendingDeposit(Base):
    """Pending deposit requests waiting for admin approval"""
    __tablename__ = "pending_deposits"
    id = Column(Integer, primary_key=True, index=True)
    sacco_id = Column(Integer, ForeignKey("saccos.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    payment_method = Column(String(50), nullable=True)
    description = Column(String(200), nullable=True)
    reference_number = Column(String(100), nullable=True)
    status = Column(String(20), default="pending")
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approval_notes = Column(String(500), nullable=True)
    rejection_reason = Column(String(500), nullable=True)
    
    # Relationships - Simple one-way
    sacco = relationship("Sacco", back_populates="pending_deposits")
    user = relationship("User", foreign_keys=[user_id], overlaps="pending_deposits")
    approver = relationship("User", foreign_keys=[approved_by], overlaps="approved_deposits")
    
    def approve(self, approver_id, notes=None):
        """Approve the deposit and create actual savings record"""
        self.status = "approved"
        self.approved_by = approver_id
        self.approved_at = datetime.datetime.utcnow()
        self.approval_notes = notes


class Saving(Base):
    __tablename__ = "savings"
    id = Column(Integer, primary_key=True, index=True)
    sacco_id = Column(Integer, ForeignKey("saccos.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    payment_method: Mapped[PaymentMethodEnum] = mapped_column(Enum(PaymentMethodEnum), default=PaymentMethodEnum.CASH)
    description = Column(String(200), nullable=True)
    reference_number = Column(String(100), nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    pending_deposit_id = Column(Integer, ForeignKey("pending_deposits.id"), nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships - Simple one-way
    sacco = relationship("Sacco", back_populates="savings")
    user = relationship("User", foreign_keys=[user_id], overlaps="savings")
    approver = relationship("User", foreign_keys=[approved_by], overlaps="approved_deposits")
    pending_deposit = relationship("PendingDeposit", foreign_keys=[pending_deposit_id])


class Loan(Base):
    __tablename__ = "loans"
    id = Column(Integer, primary_key=True, index=True)
    sacco_id = Column(Integer, ForeignKey("saccos.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    term = Column(Integer, nullable=True)
    interest_rate = Column(Float, default=12.0)
    purpose = Column(String(200), nullable=True)
    status = Column(String, default="pending")
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Interest tracking fields
    total_interest = Column(Float, default=0.0)
    total_payable = Column(Float, default=0.0)
    total_paid = Column(Float, default=0.0)
    
    # Audit trail fields
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approval_notes = Column(String(500), nullable=True)
    
    # Relationships - Simple one-way
    sacco = relationship("Sacco", back_populates="loans")
    user = relationship("User", foreign_keys=[user_id], overlaps="loans")
    approver = relationship("User", foreign_keys=[approved_by], overlaps="approved_loans")
    payments = relationship("LoanPayment", back_populates="loan", cascade="all, delete-orphan")
    
    def calculate_interest(self):
        """Calculate total interest based on amount, term, and rate"""
        self.total_interest = (self.amount * self.interest_rate * self.term) / (12 * 100)
        self.total_payable = self.amount + self.total_interest
        return self.total_interest
    
    def calculate_monthly_payment(self):
        """Calculate monthly payment amount"""
        if self.term > 0:
            return self.total_payable / self.term
        return 0


class LoanPayment(Base):
    __tablename__ = "loan_payments"
    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=False)
    sacco_id = Column(Integer, ForeignKey("saccos.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    payment_method = Column(String(50), nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    loan = relationship("Loan", back_populates="payments")
    sacco = relationship("Sacco", back_populates="loan_payments")
    user = relationship("User", foreign_keys=[user_id], overlaps="loan_payments")


class Log(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    sacco_id = Column(Integer, ForeignKey("saccos.id"), nullable=True)
    action = Column(String, nullable=False)
    details = Column(String(500), nullable=True)
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], overlaps="logs")
    sacco = relationship("Sacco", foreign_keys=[sacco_id], back_populates="logs")


class ExternalLoan(Base):
    __tablename__ = "external_loans"
    id = Column(Integer, primary_key=True, index=True)
    sacco_id = Column(Integer, ForeignKey("saccos.id"), nullable=False)
    amount = Column(Float, nullable=False)
    term = Column(Integer, nullable=False)
    interest_rate = Column(Float, default=15.0)
    purpose = Column(String(200), nullable=True)
    status = Column(String(20), default="pending")
    collateral_description = Column(String(500), nullable=False)
    collateral_value = Column(Float, nullable=False)
    guarantor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    borrower_name = Column(String(200), nullable=False)
    borrower_contact = Column(String(100), nullable=False)
    borrower_national_id = Column(String(50), nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Interest tracking fields
    total_interest = Column(Float, default=0.0)
    total_payable = Column(Float, default=0.0)
    total_paid = Column(Float, default=0.0)
    
    # Audit trail
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approval_notes = Column(String(500), nullable=True)
    
    # Relationships
    sacco = relationship("Sacco", back_populates="external_loans")
    guarantor = relationship("User", foreign_keys=[guarantor_id], overlaps="guaranteed_external_loans")
    approver = relationship("User", foreign_keys=[approved_by])
    payments = relationship("ExternalLoanPayment", back_populates="external_loan", cascade="all, delete-orphan")
    
    def calculate_interest(self):
        """Calculate total interest based on amount, term, and rate"""
        self.total_interest = (self.amount * self.interest_rate * self.term) / (12 * 100)
        self.total_payable = self.amount + self.total_interest
        return self.total_interest
    
    def calculate_monthly_payment(self):
        """Calculate monthly payment amount"""
        if self.term > 0:
            return self.total_payable / self.term
        return 0


class ExternalLoanPayment(Base):
    __tablename__ = "external_loan_payments"
    id = Column(Integer, primary_key=True, index=True)
    external_loan_id = Column(Integer, ForeignKey("external_loans.id"), nullable=False)
    amount = Column(Float, nullable=False)
    payment_method = Column(String(50), nullable=True)
    reference_number = Column(String(100), nullable=True)
    notes = Column(String(200), nullable=True)
    recorded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    external_loan = relationship("ExternalLoan", back_populates="payments")
    recorder = relationship("User", foreign_keys=[recorded_by], overlaps="recorded_external_loan_payments")


class SystemSetting(Base):
    __tablename__ = "system_settings"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True)
    value = Column(String)
    description = Column(String)
	
# backend/models.py - Enhanced referral system
class ReferralType(str, enum.Enum):
    SACCO_REFERRAL = "SACCO_REFERRAL"      # Referring a new SACCO to the platform
    MEMBER_REFERRAL = "MEMBER_REFERRAL"    # Referring a new member to a SACCO
    AGENT_REFERRAL = "AGENT_REFERRAL"      # Referring a new agent/marketer


# backend/models.py - Add ReferralCommission model

class ReferralCommission(Base):
    __tablename__ = "referral_commissions"
    id = Column(Integer, primary_key=True, index=True)
    referrer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    referred_entity_type = Column(String(20), nullable=False)  # 'sacco', 'member', 'agent'
    referred_entity_id = Column(Integer, nullable=False)
    referral_type = Column(String(20), nullable=False)  # 'SACCO_REFERRAL', 'MEMBER_REFERRAL', 'AGENT_REFERRAL'
    source = Column(String(50), nullable=False)  # 'sacco_subscription', 'member_deposit', 'loan_interest'
    source_id = Column(Integer, nullable=True)
    amount = Column(Float, nullable=False)
    percentage = Column(Float, nullable=False)
    status = Column(String(20), default="pending")  # pending, paid, cancelled
    paid_at = Column(DateTime, nullable=True)
    paid_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    notes = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    referrer = relationship("User", foreign_keys=[referrer_id])
    payer = relationship("User", foreign_keys=[paid_by])