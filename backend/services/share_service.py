# backend/services/share_service.py
"""
Share Capital Service Layer
Handles business logic for share subscriptions and management
"""
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from ..models import User
from ..models.share import Share, ShareType, ShareTransaction, ShareTransactionType, ShareClass
from ..services.user_service import get_user

logger = logging.getLogger(__name__)


def create_share_type(
    db: Session,
    sacco_id: int,
    name: str,
    class_type: str,
    par_value: float,
    minimum_shares: int = 1,
    maximum_shares: int = None,
    is_voting: bool = True,
    dividend_rate: float = 0.0
) -> ShareType:
    """Create a new share type for a SACCO"""
    # Validate class type
    try:
        class_enum = ShareClass(class_type)
    except ValueError:
        raise ValueError(f"Invalid share class type: {class_type}")
    
    share_type = ShareType(
        sacco_id=sacco_id,
        name=name,
        class_type=class_enum,
        par_value=par_value,
        minimum_shares=minimum_shares,
        maximum_shares=maximum_shares,
        is_voting=is_voting,
        dividend_rate=dividend_rate
    )
    
    db.add(share_type)
    db.commit()
    db.refresh(share_type)
    
    return share_type


def subscribe_to_shares(
    db: Session,
    user_id: int,
    sacco_id: int,
    share_type_id: int,
    quantity: int,
    total_amount: float,
    payment_method: str,
    reference_number: str = None
) -> Share:
    """Subscribe a member to shares"""
    # Get or create share record for this member and share type
    share = db.query(Share).filter(
        Share.user_id == user_id,
        Share.sacco_id == sacco_id,
        Share.share_type_id == share_type_id
    ).first()
    
    if not share:
        share = Share(
            user_id=user_id,
            sacco_id=sacco_id,
            share_type_id=share_type_id,
            quantity=0,
            total_value=0
        )
        db.add(share)
    
    # Record the transaction
    transaction = ShareTransaction(
        share_id=share.id,
        user_id=user_id,
        sacco_id=sacco_id,
        transaction_type=ShareTransactionType.SUBSCRIPTION,
        quantity=quantity,
        price_per_share=total_amount / quantity,
        total_amount=total_amount,
        payment_method=payment_method,
        reference_number=reference_number
    )
    db.add(transaction)
    
    # Update share holdings
    share.quantity += quantity
    share.total_value += total_amount
    share.last_updated = datetime.utcnow()
    
    db.commit()
    db.refresh(share)
    
    return share


def transfer_shares(
    db: Session,
    from_user_id: int,
    to_user_id: int,
    share_type_id: int,
    quantity: int,
    transfer_reason: str = None
) -> ShareTransaction:
    """Transfer shares from one member to another"""
    # Get source share
    source_share = db.query(Share).filter(
        Share.user_id == from_user_id,
        Share.share_type_id == share_type_id
    ).first()
    
    if not source_share or source_share.quantity < quantity:
        raise ValueError("Insufficient shares to transfer")
    
    # Get or create destination share
    dest_share = db.query(Share).filter(
        Share.user_id == to_user_id,
        Share.share_type_id == share_type_id
    ).first()
    
    if not dest_share:
        dest_share = Share(
            user_id=to_user_id,
            sacco_id=source_share.sacco_id,
            share_type_id=share_type_id,
            quantity=0,
            total_value=0
        )
        db.add(dest_share)
    
    # Calculate value
    value_per_share = source_share.total_value / source_share.quantity
    transfer_value = quantity * value_per_share
    
    # Record transfer transaction (for source)
    transaction = ShareTransaction(
        share_id=source_share.id,
        user_id=from_user_id,
        sacco_id=source_share.sacco_id,
        transaction_type=ShareTransactionType.TRANSFER,
        quantity=-quantity,  # Negative for outgoing
        price_per_share=value_per_share,
        total_amount=-transfer_value,
        notes=f"Transferred to user {to_user_id}. {transfer_reason or ''}"
    )
    db.add(transaction)
    
    # Record transfer transaction (for destination)
    dest_transaction = ShareTransaction(
        share_id=dest_share.id,
        user_id=to_user_id,
        sacco_id=source_share.sacco_id,
        transaction_type=ShareTransactionType.TRANSFER,
        quantity=quantity,
        price_per_share=value_per_share,
        total_amount=transfer_value,
        notes=f"Received from user {from_user_id}. {transfer_reason or ''}"
    )
    db.add(dest_transaction)
    
    # Update holdings
    source_share.quantity -= quantity
    source_share.total_value -= transfer_value
    
    dest_share.quantity += quantity
    dest_share.total_value += transfer_value
    
    db.commit()
    
    return transaction


def get_member_share_holdings(db: Session, user_id: int) -> list:
    """Get all share holdings for a member"""
    shares = db.query(Share).filter(
        Share.user_id == user_id,
        Share.is_active == True
    ).all()
    
    result = []
    for share in shares:
        result.append({
            "id": share.id,
            "share_type_id": share.share_type_id,
            "share_type_name": share.share_type.name if share.share_type else "Unknown",
            "class_type": share.share_type.class_type.value if share.share_type else None,
            "quantity": share.quantity,
            "par_value": share.share_type.par_value if share.share_type else 0,
            "total_value": share.total_value,
            "is_voting": share.share_type.is_voting if share.share_type else False,
            "dividend_rate": share.share_type.dividend_rate if share.share_type else 0
        })
    
    return result


def get_share_transaction_history(db: Session, user_id: int, limit: int = 50, offset: int = 0):
    """Get share transaction history for a member"""
    return db.query(ShareTransaction).filter(
        ShareTransaction.user_id == user_id
    ).order_by(ShareTransaction.transaction_date.desc()).offset(offset).limit(limit).all()


def withdraw_shares(
    db: Session,
    user_id: int,
    share_type_id: int,
    quantity: int,
    withdrawal_reason: str = None,
    bank_details: dict = None
) -> ShareTransaction:
    """
    Withdraw/redeem shares for a member
    
    Args:
        db: Database session
        user_id: Member ID
        share_type_id: Type of shares to withdraw
        quantity: Number of shares to withdraw
        withdrawal_reason: Reason for withdrawal (optional)
        bank_details: Bank account for refund (optional)
    
    Returns:
        ShareTransaction record of the withdrawal
    
    Raises:
        ValueError: If insufficient shares or invalid share
    """
    from datetime import datetime
    
    # Get member's share holding
    share = db.query(Share).filter(
        Share.user_id == user_id,
        Share.share_type_id == share_type_id,
        Share.is_active == True
    ).first()
    
    if not share:
        raise ValueError(f"No active share holdings found for share type {share_type_id}")
    
    if share.quantity < quantity:
        raise ValueError(
            f"Insufficient shares. You have {share.quantity} shares but requested {quantity} withdrawal."
        )
    
    # Get share type for par value
    share_type = db.query(ShareType).filter(
        ShareType.id == share_type_id
    ).first()
    
    if not share_type:
        raise ValueError("Share type not found")
    
    # Calculate refund value based on current total_value
    value_per_share = share.total_value / share.quantity if share.quantity > 0 else share_type.par_value
    refund_amount = quantity * value_per_share
    
    # Create withdrawal transaction
    transaction = ShareTransaction(
        share_id=share.id,
        user_id=user_id,
        sacco_id=share.sacco_id,
        transaction_type=ShareTransactionType.WITHDRAWAL,
        quantity=-quantity,  # Negative for withdrawal
        price_per_share=value_per_share,
        total_amount=-refund_amount,  # Negative (outgoing)
        payment_method=bank_details.get("payment_method", "bank_transfer") if bank_details else "bank_transfer",
        reference_number=bank_details.get("reference_number") if bank_details else None,
        notes=f"Share withdrawal. Reason: {withdrawal_reason or 'Not specified'}"
    )
    db.add(transaction)
    
    # Update member's share holding
    share.quantity -= quantity
    share.total_value -= refund_amount
    
    # If no shares left, mark as inactive
    if share.quantity == 0:
        share.is_active = False
    
    # Update timestamp
    share.last_updated = datetime.utcnow()
    
    db.commit()
    db.refresh(transaction)
    
    return transaction


def get_withdrawal_options(db: Session, user_id: int, sacco_id: int) -> list:
    """
    Get all shares available for withdrawal
    
    Returns:
        List of shares with details suitable for withdrawal form
    """
    shares = db.query(Share).filter(
        Share.user_id == user_id,
        Share.sacco_id == sacco_id,
        Share.is_active == True,
        Share.quantity > 0
    ).all()
    
    options = []
    for share in shares:
        if share.share_type:
            options.append({
                "id": share.id,
                "share_type_id": share.share_type_id,
                "share_type_name": share.share_type.name,
                "quantity_available": share.quantity,
                "total_value": share.total_value,
                "value_per_share": share.total_value / share.quantity if share.quantity > 0 else 0,
                "class_type": share.share_type.class_type.value if share.share_type.class_type else None
            })
    
    return options