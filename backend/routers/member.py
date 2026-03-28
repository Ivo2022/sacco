import uuid  # ← Add this import
import shutil
from fastapi import APIRouter, Request, Form, Depends, HTTPException, File, UploadFile
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..core.dependencies import get_db, get_current_user
from ..models import User, Saving, Loan, LoanPayment, Log, PendingDeposit
from datetime import datetime, timedelta
from ..utils.helpers import get_template_helpers, check_sacco_status
import os
from typing import Optional
from ..services.user_service import create_user
from ..utils.logger import create_log

router = APIRouter()
templates = Jinja2Templates(directory="backend/templates")

# Configure upload directory
UPLOAD_DIR = "backend/static/uploads/profiles"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.get("/member/dashboard", response_class=HTMLResponse)
def member_dashboard(
    request: Request, 
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
	# Check SACCO status
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    
    # Calculate balance
    total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id,
        Saving.type == 'deposit'
    ).scalar() or 0
    
    total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id,
        Saving.type == 'withdraw'
    ).scalar() or 0
    
    balance = total_deposits - total_withdrawals
    print(f"Balance: {balance}")
    
    # Get recent transactions
    transactions = db.query(Saving).filter(
        Saving.user_id == user.id
    ).order_by(Saving.timestamp.desc()).limit(10).all()
    print(f"Transactions found: {len(transactions)}")
    
    # Get loans (ORIGINAL ORM objects)
    loans_orm = db.query(Loan).filter(
        Loan.user_id == user.id
    ).order_by(Loan.timestamp.desc()).all()
    print(f"Loans found: {len(loans_orm)}")
    
    # Convert to dictionary format with repaid and outstanding (SAME AS LOANS PAGE)
    loans = []
    for loan in loans_orm:
        # Calculate repaid amount (SAME AS LOANS PAGE)
        repaid = db.query(func.coalesce(func.sum(LoanPayment.amount), 0)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0.0
        
        # Calculate outstanding (SAME AS LOANS PAGE)
        outstanding = max(0.0, loan.amount - repaid)
        
        # Debug: Compare with loans page values
        print(f"\n  Loan #{loan.id}:")
        print(f"    Amount: {loan.amount}")
        print(f"    Repaid: {repaid}")
        print(f"    Outstanding: {outstanding}")
        print(f"    Status: {loan.status}")
        
        # Create dictionary with same structure as loans page expects
        loan_dict = {
            "id": loan.id,
            "amount": loan.amount,
            "term": loan.term,
            "status": loan.status,
            "timestamp": loan.timestamp,
            "repaid": float(repaid),  # ← This matches loans.html
            "outstanding": float(outstanding)  # ← This matches loans.html
        }
        loans.append(loan_dict)
    
    # Calculate totals for summary cards (using the same data)
    total_repaid = sum(loan["repaid"] for loan in loans)
    total_outstanding = sum(loan["outstanding"] for loan in loans)
    
    # Filter active loans (same logic as loans.html)
    active_loans_list = [loan for loan in loans if loan["status"] in ['approved', 'partial']]
    active_loans_count = len(active_loans_list)
    active_loans_total = sum(loan["amount"] for loan in active_loans_list)
    active_loans_outstanding = sum(loan["outstanding"] for loan in active_loans_list)
    
    print(f"\n=== Summary Totals ===")
    print(f"Total Repaid (all loans): UGX {total_repaid:.2f}")
    print(f"Total Outstanding (all loans): UGX {total_outstanding:.2f}")
    print(f"Active Loans: {active_loans_count}")
    print(f"Active Loans Outstanding: UGX {active_loans_outstanding:.2f}")
    
    sacco = user.sacco
    print(f"SACCO: {sacco.name if sacco else 'None'}")
    # Get all template helpers
    helpers = get_template_helpers()
	
    return templates.TemplateResponse(
        "client/dashboard.html", 
        {
            "request": request, 
            "user": user, 
            "sacco": sacco,
            "balance": balance,
            "transactions": transactions,
            "loans": loans,  # ← Now has repaid and outstanding attributes
            "active_loans": active_loans_list,  # For detailed list if needed
            "summary": {
                "total_repaid": total_repaid,
                "total_outstanding": total_outstanding,
                "active_loans_count": active_loans_count,
                "active_loans_outstanding": active_loans_outstanding
            },
			**helpers
        }
    )

@router.get("/member/profile", response_class=HTMLResponse)
def view_profile(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
		# Check SACCO status
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
		
    """Display member profile page with edit form"""
    
    # Calculate member statistics for the profile
    total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id,
        Saving.type == 'deposit'
    ).scalar() or 0
    
    total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id,
        Saving.type == 'withdraw'
    ).scalar() or 0
    
    balance = total_deposits - total_withdrawals
    
    # Get active loans count
    active_loans = db.query(Loan).filter(
        Loan.user_id == user.id,
        Loan.status.in_(['approved', 'partial'])
    ).count()
    
    # Get total repaid
    total_repaid = db.query(func.coalesce(func.sum(LoanPayment.amount), 0)).filter(
        LoanPayment.user_id == user.id
    ).scalar() or 0
	
    helpers = get_template_helpers()
	
    return templates.TemplateResponse(
        "client/profile.html",
        {
            "request": request,
            "user": user,
            "balance": balance,
            "active_loans": active_loans,
            "total_repaid": total_repaid,
            "member_since": user.created_at.strftime('%B %Y') if user.created_at else 'N/A',
			**helpers
        }
    )

@router.post("/member/profile/update")
async def update_profile(
    request: Request,
    full_name: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    date_of_birth: Optional[str] = Form(None),
    national_id: Optional[str] = Form(None),
    profile_picture: Optional[UploadFile] = File(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
		# Check SACCO status
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
		
    """Update member profile information"""
    
    # Helper function to get balance
    def get_balance():
        total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
            Saving.user_id == user.id,
            Saving.type == 'deposit'
        ).scalar() or 0
        total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
            Saving.user_id == user.id,
            Saving.type == 'withdraw'
        ).scalar() or 0
        return total_deposits - total_withdrawals
    
    # Helper function to get active loans count
    def get_active_loans():
        return db.query(Loan).filter(
            Loan.user_id == user.id,
            Loan.status.in_(['approved', 'partial'])
        ).count()
    
    # Helper function to get total repaid
    def get_total_repaid():
        return db.query(func.coalesce(func.sum(LoanPayment.amount), 0)).filter(
            LoanPayment.user_id == user.id
        ).scalar() or 0
	
    try:
        # Update basic information
        if full_name:
            user.full_name = full_name
        if phone:
            user.phone = phone
        if address:
            user.address = address
        if national_id:
            user.national_id = national_id
        
        # Handle date of birth
        if date_of_birth:
            try:
                user.date_of_birth = datetime.strptime(date_of_birth, '%Y-%m-%d')
            except ValueError:
                pass
        
        # Handle email change (check for uniqueness)
        if email and email != user.email:
            existing_user = db.query(User).filter(User.email == email).first()
            if existing_user:
                helpers = get_template_helpers()
                return templates.TemplateResponse(
                    "client/profile.html",
                    {
                        "request": request,
                        "user": user,
                        "balance": get_balance(),
                        "active_loans": get_active_loans(),
                        "total_repaid": get_total_repaid(),
                        "member_since": user.created_at.strftime('%B %Y') if user.created_at else 'N/A',
                        "error": "Email already exists. Please use a different email address.",
                        "success": None,
                        **helpers
                    }
                )
            user.email = email
        
        # Handle profile picture upload
        if profile_picture and profile_picture.filename:
            # Validate file type
            allowed_types = ['image/jpeg', 'image/png', 'image/jpg', 'image/gif']
            if profile_picture.content_type not in allowed_types:
                helpers = get_template_helpers()
                return templates.TemplateResponse(
                    "client/profile.html",
                    {
                        "request": request,
                        "user": user,
                        "balance": get_balance(),
                        "active_loans": get_active_loans(),
                        "total_repaid": get_total_repaid(),
                        "member_since": user.created_at.strftime('%B %Y') if user.created_at else 'N/A',
                        "error": "Invalid file type. Please upload JPEG, PNG, or GIF images.",
                        "success": None,
                        **helpers
                    }
                )
            
            # Generate unique filename
            file_extension = profile_picture.filename.split('.')[-1]
            filename = f"user_{user.id}_{uuid.uuid4().hex[:8]}.{file_extension}"
            file_path = os.path.join(UPLOAD_DIR, filename)
            
            # Save file
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(profile_picture.file, buffer)
            
            # Remove old profile picture if exists
            if user.profile_picture:
                old_path = os.path.join(UPLOAD_DIR, user.profile_picture)
                if os.path.exists(old_path):
                    os.remove(old_path)
            
            # Update user with new profile picture path
            user.profile_picture = filename
        
        # Commit changes
        db.commit()
        db.refresh(user)
        helpers = get_template_helpers()
        return templates.TemplateResponse(
            "client/profile.html",
            {
                "request": request,
                "user": user,
                "balance": get_balance(),
                "active_loans": get_active_loans(),
                "total_repaid": get_total_repaid(),
                "member_since": user.created_at.strftime('%B %Y') if user.created_at else 'N/A',
                "success": "Profile updated successfully!",
                "error": None,
                **helpers
            }
        )
        
    except Exception as e:
        db.rollback()
        helpers = get_template_helpers()
        return templates.TemplateResponse(
            "client/profile.html",
            {
                "request": request,
                "user": user,
                "balance": get_balance(),
                "active_loans": get_active_loans(),
                "total_repaid": get_total_repaid(),
                "member_since": user.created_at.strftime('%B %Y') if user.created_at else 'N/A',
                "error": f"An error occurred: {str(e)}",
                "success": None,
                **helpers
            }
        )

@router.post("/member/profile/change-password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
		# Check SACCO status
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    """Change member password"""
    
    # Verify current password
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    if not pwd_context.verify(current_password, user.password_hash):
        return templates.TemplateResponse(
            "client/profile.html",
            {
                "request": request,
                "user": user,
                "password_error": "Current password is incorrect.",
                "success": None
            }
        )
    
    # Validate new password
    if len(new_password) < 6:
        return templates.TemplateResponse(
            "client/profile.html",
            {
                "request": request,
                "user": user,
                "password_error": "New password must be at least 6 characters long.",
                "success": None
            }
        )
    
    if new_password != confirm_password:
        return templates.TemplateResponse(
            "client/profile.html",
            {
                "request": request,
                "user": user,
                "password_error": "New passwords do not match.",
                "success": None
            }
        )
    
    # Update password
    user.password_hash = pwd_context.hash(new_password)
    user.password_reset_required = False
    
    db.commit()
    helpers = get_template_helpers()
    return templates.TemplateResponse(
        "client/profile.html",
        {
            "request": request,
            "user": user,
            "password_success": "Password changed successfully!",
            "success": None,
			**helpers
        }
    )


@router.get("/member/savings", response_class=HTMLResponse)
def view_savings(
    request: Request, 
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
		# Check SACCO status
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    # Calculate balance
    total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id,
        Saving.type == 'deposit',
		Saving.approved_by.isnot(None)  # Only approved deposits
    ).scalar() or 0
    
    total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id,
        Saving.type == 'withdraw',
		Saving.approved_by.isnot(None)  # Only approved deposits
    ).scalar() or 0
    
    balance = total_deposits - total_withdrawals
    
    # Get pending deposits for this user
    pending_deposits = db.query(PendingDeposit).filter(
        PendingDeposit.user_id == user.id,
        PendingDeposit.status == "pending"
    ).order_by(PendingDeposit.timestamp.desc()).all()
	
    # Get all transactions
    transactions = db.query(Saving).filter(
        Saving.user_id == user.id
    ).order_by(Saving.timestamp.desc()).all()
    
	# Get all template helpers
    helpers = get_template_helpers()
	
    return templates.TemplateResponse(
        "client/savings.html",  # Keep template name consistent
        {
            "request": request, 
            "user": user, 
            "balance": balance, 
            "transactions": transactions,
			"pending_deposits": pending_deposits,
            "now": datetime.utcnow(),
			"session": request.session,  # ← Add this line to pass session to template
            **helpers  # Unpack all helpers into context
        }
    )

@router.post("/member/savings/deposit/initiate")
async def initiate_deposit(
    request: Request, 
    amount: float = Form(...),
    payment_method: str = Form(...),
    reference_number: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
		# Check SACCO status
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    """Initiate a deposit request that needs admin approval"""
    
    if amount <= 0:
        request.session["flash_message"] = "Amount must be positive"
        request.session["flash_type"] = "danger"
        return RedirectResponse("/member/savings", status_code=303)
    
    # Create pending deposit
    pending = PendingDeposit(
        sacco_id=user.sacco_id,
        user_id=user.id,
        amount=amount,
        payment_method=payment_method,
        description=description,
        reference_number=reference_number,
        status="pending",
        timestamp=datetime.utcnow()
    )
    
    db.add(pending)
    db.commit()
    
    # Create audit log
    create_log(
        db,
        action="DEPOSIT_INITIATED",
        user_id=user.id,
        sacco_id=user.sacco_id,
        details=f"Member {user.email} initiated deposit of UGX {amount:,.2f}",
        ip_address=request.client.host if request.client else None
    )
    
    request.session["flash_message"] = f"Deposit request of UGX {amount:,.2f} submitted for approval"
    request.session["flash_type"] = "success"
    
    return RedirectResponse("/member/savings", status_code=303)


@router.post("/member/savings/deposit/{pending_id}/cancel")
def cancel_pending_deposit(
    pending_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
		# Check SACCO status
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    """Cancel a pending deposit request"""
    
    pending = db.query(PendingDeposit).filter(
        PendingDeposit.id == pending_id,
        PendingDeposit.user_id == user.id,
        PendingDeposit.status == "pending"
    ).first()
    
    if not pending:
        raise HTTPException(status_code=404, detail="Pending deposit not found")
    
    pending.status = "cancelled"
    db.commit()
    
    request.session["flash_message"] = "Deposit request cancelled"
    request.session["flash_type"] = "info"
    
    return RedirectResponse("/member/savings", status_code=303)

@router.post("/member/savings/deposit")
def deposit(
    request: Request, 
    amount: float = Form(...), 
	payment_method: str = Form(...),  # ← NEW: Add payment method parameter
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
		# Check SACCO status
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
		
    if amount <= 0:
        # Get balance for template
        total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
            Saving.user_id == user.id, Saving.type == 'deposit'
        ).scalar() or 0
        total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
            Saving.user_id == user.id, Saving.type == 'withdraw'
        ).scalar() or 0
        balance = total_deposits - total_withdrawals
        transactions = db.query(Saving).filter(Saving.user_id == user.id).order_by(Saving.timestamp.desc()).all()
        
        return templates.TemplateResponse(
            "client/savings.html", 
            {
                "request": request, 
                "user": user, 
                "balance": balance, 
                "transactions": transactions,
                "error": "Amount must be positive"
            }
        )
    
    # Create deposit transaction - ADD sacco_id here
    deposit = Saving(
        sacco_id=user.sacco_id,  # ← THIS LINE WAS MISSING
        user_id=user.id,
        type='deposit',
        amount=amount,
		payment_method=payment_method
    )
    db.add(deposit)
    db.commit()
    
    create_log(
        db,
        action="DEPOSIT_MADE",
        user_id=user.id,
        sacco_id=user.sacco_id,
        details=f"Deposit of UGX {amount:,.2f} made via {payment_method}",
        ip_address=request.client.host if request.client else None
    )
	
    return RedirectResponse("/member/savings", status_code=303)


@router.post("/member/savings/withdraw")
def withdraw(
    request: Request, 
    amount: float = Form(...), 
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
		# Check SACCO status
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
		
    # First check if user has enough balance
    total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id, Saving.type == 'deposit'
    ).scalar() or 0
    total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id, Saving.type == 'withdraw'
    ).scalar() or 0
    balance = total_deposits - total_withdrawals
    
    if amount <= 0:
        return templates.TemplateResponse(
            "client/savings.html", 
            {
                "request": request, 
                "user": user, 
                "balance": balance,
                "transactions": db.query(Saving).filter(Saving.user_id == user.id).order_by(Saving.timestamp.desc()).all(),
                "error": "Amount must be positive"
            }
        )
    
    if amount > balance:
        return templates.TemplateResponse(
            "client/savings.html", 
            {
                "request": request, 
                "user": user, 
                "balance": balance,
                "transactions": db.query(Saving).filter(Saving.user_id == user.id).order_by(Saving.timestamp.desc()).all(),
                "error": "Insufficient balance"
            }
        )
    
    # Create withdrawal transaction - ADD sacco_id here as well
    withdrawal = Saving(
        sacco_id=user.sacco_id,  # ← ADD THIS LINE
        user_id=user.id,
        type='withdraw',
        amount=amount
    )
    db.add(withdrawal)
    db.commit()
    
    return RedirectResponse("/member/savings", status_code=303)

@router.get("/member/loans", response_class=HTMLResponse)
def view_loans(
    request: Request, 
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
		# Check SACCO status
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
		
    # Get user's loans as ORM objects
    loans_orm = db.query(Loan).filter(
        Loan.user_id == user.id
    ).order_by(Loan.timestamp.desc()).all()
    
    # Convert to dictionary format that matches the template's expectations
    loans = []
    
    for loan in loans_orm:
        # Calculate repaid amount
        repaid = db.query(func.coalesce(func.sum(LoanPayment.amount), 0)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0.0
        
        outstanding = max(0.0, loan.amount - repaid)
        
        loans.append({
            "id": loan.id,
            "amount": loan.amount,
            "term": loan.term,
            "status": loan.status,
            "timestamp": loan.timestamp.strftime("%Y-%m-%d %H:%M:%S") if loan.timestamp else "",
            "repaid": float(repaid),
            "outstanding": outstanding,
            "purpose": loan.purpose if hasattr(loan, 'purpose') else None,
            "interest_rate": 12  # Default interest rate, can be fetched from loan if available
        })
    
    # Get payment history for all loans (as ORM objects)
    payments_history_orm = db.query(LoanPayment).filter(
        LoanPayment.user_id == user.id
    ).order_by(LoanPayment.timestamp.desc()).all()
    
    # Convert payment history to dictionary format for template
    payments_history = []
    for payment in payments_history_orm:
        # Get the associated loan to display loan ID
        loan = db.query(Loan).filter(Loan.id == payment.loan_id).first()
        payments_history.append({
            "id": payment.id,
            "loan_id": payment.loan_id,
            "amount": payment.amount,
            "payment_method": getattr(payment, 'payment_method', 'savings'),  # Default to savings if not set
            "reference": getattr(payment, 'reference', None),
            "timestamp": payment.timestamp.strftime("%Y-%m-%d %H:%M:%S") if payment.timestamp else "",
            "date": payment.timestamp.strftime("%Y-%m-%d") if payment.timestamp else ""
        })
    
    # Calculate total payments
    total_payments = db.query(func.coalesce(func.sum(LoanPayment.amount), 0)).filter(
        LoanPayment.user_id == user.id
    ).scalar() or 0
    
    # Calculate user's current savings balance
    total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id,
        Saving.type == 'deposit'
    ).scalar() or 0.0
    
    total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id,
        Saving.type == 'withdraw'
    ).scalar() or 0.0
    
    balance = total_deposits - total_withdrawals
    
    # Get recent transactions (as dictionaries for template)
    recent_transactions_raw = db.query(Saving).filter(
        Saving.user_id == user.id
    ).order_by(Saving.timestamp.desc()).limit(5).all()
    
    recent_transactions = []
    for t in recent_transactions_raw:
        recent_transactions.append({
            "type": t.type,
            "amount": t.amount,
            "timestamp": t.timestamp.strftime("%Y-%m-%d %H:%M:%S") if t.timestamp else "",
            "payment_method": getattr(t, 'payment_method', None)
        })
    
    # Generate notifications
    notifications = []
    
    # Check for overdue loans
    for loan in loans:
        if loan["status"] in ["approved", "partial"] and loan["outstanding"] > 0:
            # Check if there are any recent payments
            last_payment = db.query(func.max(LoanPayment.timestamp)).filter(
                LoanPayment.loan_id == loan["id"]
            ).scalar()
            
            if last_payment:
                if datetime.utcnow() - last_payment > timedelta(days=30):
                    notifications.append({
                        "icon": "exclamation-triangle",
                        "message": f"Loan #{loan['id']} payment is overdue. Outstanding: UGX {loan['outstanding']:.2f}",
                        "due_date": None
                    })
    
    # Check for low savings
    if balance < 10000:
        notifications.append({
            "icon": "piggy-bank",
            "message": f"Your savings balance (UGX {balance:.2f}) is low. Consider making a deposit.",
            "due_date": None
        })
    
    # Check for pending loan requests
    pending_loans = [l for l in loans if l["status"] == "pending"]
    if pending_loans:
        notifications.append({
            "icon": "clock",
            "message": f"You have {len(pending_loans)} pending loan request(s) awaiting review.",
            "due_date": None
        })
    helpers = get_template_helpers()
    return templates.TemplateResponse(
        "client/loans.html",
        {
            "request": request,
            "user": user,
            "loans": loans,
            "balance": balance,
            "payments_history": payments_history,  # Now properly formatted
            "total_payments": total_payments,
            "current_savings": balance,
            "notifications": notifications,
            "recent_transactions": recent_transactions,
			**helpers
        }
    )
	
@router.post("/member/loan/request")
def request_loan(
    request: Request,
    amount: float = Form(...),
    term: int = Form(12),
    purpose: str = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
		# Check SACCO status
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
	
    # Check if user is allowed to apply for loans
    if not user.can_apply_for_loans:
        return templates.TemplateResponse(
            "client/loans.html",
            {
                "request": request,
                "user": user,
                "error": "Your account is not authorized to apply for loans. If you are a staff member, please use your member account (if created) or contact the administrator.",
                "loans": []
            }
        )
	# Validate amount
    if amount <= 0:
        return templates.TemplateResponse(
            "client/loans.html",
            {
                "request": request,
                "user": user,
                "error": "Loan amount must be positive"
            }
        )
    
    # Validate term
    if term <= 0 or term > 60:
        return templates.TemplateResponse(
            "client/loans.html",
            {
                "request": request,
                "user": user,
                "error": "Loan term must be between 1 and 60 months",
                "loans": get_user_loans_with_repayment(db, user.id)
            }
        )
	
    # Check if user has sufficient savings (max loan 3x savings)
    total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id, Saving.type == 'deposit'
    ).scalar() or 0
    total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id, Saving.type == 'withdraw'
    ).scalar() or 0
    balance = total_deposits - total_withdrawals
    # Validate maximum loan possible
    max_loan = balance * 3
    if amount > max_loan:
        return templates.TemplateResponse(
            "client/loans.html",
            {
                "request": request,
                "user": user,
                "error": f"Maximum loan amount is UGX {max_loan:.2f} (3x your savings)"
            }
        )
    
    # Create loan request
    loan = Loan(
        sacco_id=user.sacco_id,  # ← THIS IS THE CRITICAL LINE - was missing
        user_id=user.id,
        amount=amount,
        term=term,
        status='pending',
        purpose=purpose,
		interest_rate=12.0  # 12% per annum for members
    )
    # Calculate interest
    loan.calculate_interest()
	
    db.add(loan)
    db.commit()
    create_log(
        db,
        action="LOAN_REQUESTED",
        user_id=user.id,
        sacco_id=user.sacco_id,
        details=f"Loan request of UGX {amount:,.2f} for {term} months. Purpose: {purpose or 'Not specified'}",
        ip_address=request.client.host if request.client else None
    )
    return RedirectResponse("/member/loans", status_code=303)


@router.post("/member/loan/repay")
def repay_loan(
    request: Request,
    loan_id: int = Form(...),
    amount: float = Form(...),
    payment_method: str = Form(...),  # This comes from your form
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
		# Check SACCO status
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    """Record a loan repayment - applies to total payable (principal + interest)"""
    
    if amount <= 0:
        return RedirectResponse("/member/loans?error=payment_must_be_positive", status_code=303)
    
    # Get the loan
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        return RedirectResponse("/member/loans?error=loan_not_found", status_code=303)
    
    # Check authorization
    if loan.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to repay this loan")
    
    # Check if loan is approved
    if loan.status not in ("approved", "partial"):
        return templates.TemplateResponse(
            "client/loans.html",
            {
                "request": request,
                "user": user,
                "error": "This loan is not approved or already completed",
                "loans": get_user_loans_with_repayment(db, user.id)
            }
        )
    
    # Calculate total payable (principal + interest)
    # If total_payable is not set, calculate it
    if loan.total_payable == 0:
        loan.calculate_interest()
        db.commit()
    
    # Calculate amount paid so far
    total_paid = db.query(func.coalesce(func.sum(LoanPayment.amount), 0)).filter(
        LoanPayment.loan_id == loan_id
    ).scalar() or 0
    
    # Calculate remaining balance (total payable - total paid)
    remaining = max(0.0, loan.total_payable - total_paid)
    
    if remaining <= 0:
        return RedirectResponse("/member/loans?error=loan_already_paid", status_code=303)
    
    # Cap payment amount to remaining balance
    pay_amount = min(amount, remaining)
    
    # Check if payment method is from savings
    if payment_method == "SAVINGS":
        # Calculate user's savings balance
        total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
            Saving.user_id == user.id, Saving.type == 'deposit'
        ).scalar() or 0
        total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
            Saving.user_id == user.id, Saving.type == 'withdraw'
        ).scalar() or 0
        balance = total_deposits - total_withdrawals
        
        if pay_amount > balance:
            return RedirectResponse("/member/loans?error=insufficient_savings_balance", status_code=303)
        
        # Create withdrawal from savings
        withdrawal = Saving(
            sacco_id=user.sacco_id,
            user_id=user.id,
            type='withdraw',
            amount=pay_amount,
            payment_method=payment_method,
            description=f"Loan repayment for loan #{loan_id} (Principal + Interest)"
        )
        db.add(withdrawal)
    
    # Create loan payment record
    payment = LoanPayment(
        loan_id=loan_id,
        sacco_id=user.sacco_id,
        user_id=user.id,
        amount=pay_amount,
        payment_method=payment_method
    )
    db.add(payment)
    
    # Update loan total paid
    loan.total_paid = total_paid + pay_amount
    
    # Calculate new remaining balance
    new_remaining = loan.total_payable - loan.total_paid
    
    # Update loan status based on remaining balance
    if new_remaining <= 0.01:  # Fully repaid
        loan.status = 'completed'
        payment_message = f"Loan fully repaid! Total paid: UGX {loan.total_paid:,.2f}"
    else:
        loan.status = 'partial'
        payment_message = f"Payment of UGX {pay_amount:,.2f} recorded. Remaining: UGX {new_remaining:,.2f}"
    
    db.commit()
    
    # Create audit log
    create_log(
        db,
        action="LOAN_PAYMENT",
        user_id=user.id,
        sacco_id=user.sacco_id,
        details=f"Payment of UGX {pay_amount:,.2f} recorded for loan #{loan_id}. {payment_message}",
        ip_address=request.client.host if request.client else None
    )
    
    return RedirectResponse("/member/loans?success=payment_successful", status_code=303)

@router.get("/member/inactive", response_class=HTMLResponse)
def inactive_page(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Show inactive SACCO message"""
    sacco = None
    if user.sacco_id:
        sacco = db.query(Sacco).filter(Sacco.id == user.sacco_id).first()
    
    return templates.TemplateResponse("member/inactive.html", {
        "request": request,
        "user": user,
        "sacco": sacco
    })

@router.get("/member/suspended", response_class=HTMLResponse)
def suspended_page(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Show suspended SACCO message"""
    sacco = None
    if user.sacco_id:
        sacco = db.query(Sacco).filter(Sacco.id == user.sacco_id).first()
    
    return templates.TemplateResponse("member/suspended.html", {
        "request": request,
        "user": user,
        "sacco": sacco
    })