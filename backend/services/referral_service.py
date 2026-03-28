# backend/services/referral_service.py
"""
Referral Service Module
Handles all referral-related business logic including:
- Commission calculations
- Tiered rewards
- Referral code generation
- Commission payouts
"""

from sqlalchemy.orm import Session
from datetime import datetime
from ..models import User, ReferralCommission, Log, Sacco
from ..utils.logger import create_log


class TieredReferralRewards:
    """
    Tiered commission structure to incentivize more referrals.
    Higher referral counts = higher commission rates.
    """
    
    # Tier definitions
    TIERS = {
        "bronze": {"min_ref": 0, "rate": 3.0, "description": "0-4 referrals"},
        "silver": {"min_ref": 5, "rate": 5.0, "description": "5-19 referrals"},
        "gold": {"min_ref": 20, "rate": 7.0, "description": "20-49 referrals"},
        "platinum": {"min_ref": 50, "rate": 10.0, "description": "50+ referrals"}
    }
    
    # Fixed rates for other referral types
    SACCO_REFERRAL_RATE = 15.0  # 15% for SACCO referrals
    AGENT_REFERRAL_RATE = 20.0   # 20% for agent referrals
    
    @classmethod
    def get_commission_rate(cls, user: User, referral_type: str) -> float:
        """
        Get commission rate based on referral count and type.
        
        Args:
            user: The user who made the referral
            referral_type: 'member', 'sacco', or 'agent'
        
        Returns:
            Commission rate as a percentage
        """
        
        if referral_type == "member":
            # Member referrals use tiered structure
            count = user.total_referrals or 0
            
            if count >= 50:
                rate = cls.TIERS["platinum"]["rate"]
                tier = "platinum"
            elif count >= 20:
                rate = cls.TIERS["gold"]["rate"]
                tier = "gold"
            elif count >= 5:
                rate = cls.TIERS["silver"]["rate"]
                tier = "silver"
            else:
                rate = cls.TIERS["bronze"]["rate"]
                tier = "bronze"
            
            # Optional: Log tier info for debugging
            print(f"User {user.email} in {tier} tier: {rate}% commission")
            return rate
            
        elif referral_type == "sacco":
            return cls.SACCO_REFERRAL_RATE
            
        elif referral_type == "agent":
            return cls.AGENT_REFERRAL_RATE
            
        else:
            return 0.0
    
    @classmethod
    def get_current_tier(cls, user: User) -> dict:
        """Get the current tier information for a user"""
        count = user.total_referrals or 0
        
        if count >= 50:
            return cls.TIERS["platinum"]
        elif count >= 20:
            return cls.TIERS["gold"]
        elif count >= 5:
            return cls.TIERS["silver"]
        else:
            return cls.TIERS["bronze"]
    
    @classmethod
    def get_next_tier(cls, user: User) -> dict:
        """Get the next tier requirements for a user"""
        count = user.total_referrals or 0
        
        if count < 5:
            return {"min_ref": 5, "rate": 5.0, "needed": 5 - count}
        elif count < 20:
            return {"min_ref": 20, "rate": 7.0, "needed": 20 - count}
        elif count < 50:
            return {"min_ref": 50, "rate": 10.0, "needed": 50 - count}
        else:
            return {"min_ref": None, "rate": 10.0, "needed": 0, "message": "Maximum tier reached"}


class ReferralService:
    """Main referral service handling all referral operations"""
    
    @staticmethod
    def generate_referral_code(user: User, referral_type: str) -> str:
        """
        Generate a unique referral code for a user.
        
        Args:
            user: The user to generate code for
            referral_type: 'sacco', 'member', or 'agent'
        """
        import uuid
        
        prefix = {
            'sacco': 'SACCOREF',
            'member': 'MEMBERREF',
            'agent': 'AGENTREF'
        }.get(referral_type, 'REF')
        
        code = f"{prefix}_{user.id}_{uuid.uuid4().hex[:8]}"
        return code.upper()
    
    @staticmethod
    def apply_sacco_referral(
        db: Session, 
        sacco: Sacco, 
        referral_code: str, 
        referrer: User
    ) -> dict:
        """
        Apply referral when a new SACCO is created.
        
        Returns:
            Dictionary with commission details
        """
        # Validate code type
        if not referral_code.startswith("SACCOREF_"):
            return {"success": False, "error": "Invalid SACCO referral code"}
        
        # Find referrer by code
        referrer = db.query(User).filter(
            User.sacco_referral_code == referral_code
        ).first()
        
        if not referrer:
            return {"success": False, "error": "Referrer not found"}
        
        # Link SACCO to referrer
        sacco.referred_by_id = referrer.id
        
        # Get commission rate
        commission_rate = TieredReferralRewards.get_commission_rate(
            referrer, "sacco"
        )
        
        # Calculate commission (e.g., 15% of first year subscription)
        # Assuming subscription fee of UGX 100,000/year
        subscription_fee = 100000
        commission_amount = (subscription_fee * commission_rate) / 100
        
        # Create commission record
        commission = ReferralCommission(
            referrer_id=referrer.id,
            referred_entity_type="sacco",
            referred_entity_id=sacco.id,
            referral_type="SACCO_REFERRAL",
            source="sacco_subscription",
            amount=commission_amount,
            percentage=commission_rate,
            status="pending"
        )
        db.add(commission)
        
        # Update referrer's earnings
        if not hasattr(referrer, 'sacco_referral_earnings'):
            referrer.sacco_referral_earnings = 0
        referrer.sacco_referral_earnings += commission_amount
        
        db.commit()
        
        # Create audit log
        create_log(
            db,
            action="SACCO_REFERRAL_APPLIED",
            user_id=referrer.id,
            sacco_id=sacco.id,
            details=f"Commission UGX {commission_amount:,.2f} for SACCO {sacco.name} at {commission_rate}%"
        )
        
        return {
            "success": True,
            "commission": commission_amount,
            "rate": commission_rate,
            "commission_id": commission.id
        }
    
    @staticmethod
    def apply_member_referral(
        db: Session, 
        new_member: User, 
        referral_code: str
    ) -> dict:
        """
        Apply referral when a new member joins a SACCO.
        
        Returns:
            Dictionary with referral details
        """
        # Validate code type
        if not referral_code.startswith("MEMBERREF_"):
            return {"success": False, "error": "Invalid member referral code"}
        
        # Find referrer by code
        referrer = db.query(User).filter(
            User.member_referral_code == referral_code
        ).first()
        
        if not referrer:
            return {"success": False, "error": "Referrer not found"}
        
        # Ensure they are in the same SACCO
        if referrer.sacco_id != new_member.sacco_id:
            return {"success": False, "error": "Referrer must be in the same SACCO"}
        
        # Link member to referrer
        new_member.referred_by_id = referrer.id
        
        # Update referrer's statistics
        referrer.total_referrals = (referrer.total_referrals or 0) + 1
        
        db.commit()
        
        # Get tier information for the referrer
        current_tier = TieredReferralRewards.get_current_tier(referrer)
        next_tier = TieredReferralRewards.get_next_tier(referrer)
        
        return {
            "success": True,
            "referrer_id": referrer.id,
            "current_tier": current_tier,
            "next_tier": next_tier,
            "total_referrals": referrer.total_referrals
        }
    
    @staticmethod
    def process_deposit_commission(
        db: Session, 
        member: User, 
        deposit_amount: float, 
        deposit_id: int
    ) -> dict:
        """
        Process commission when a referred member makes a deposit.
        
        Returns:
            Dictionary with commission details
        """
        if not member.referred_by_id:
            return {"success": False, "error": "No referrer found"}
        
        referrer = db.query(User).filter(User.id == member.referred_by_id).first()
        if not referrer:
            return {"success": False, "error": "Referrer not found"}
        
        # Get commission rate based on referrer's tier
        commission_rate = TieredReferralRewards.get_commission_rate(
            referrer, "member"
        )
        
        # Calculate commission
        commission_amount = (deposit_amount * commission_rate) / 100
        
        commission = ReferralCommission(
            referrer_id=referrer.id,
            referred_entity_type="member",
            referred_entity_id=member.id,
            referral_type="MEMBER_REFERRAL",
            source="member_deposit",
            source_id=deposit_id,
            amount=commission_amount,
            percentage=commission_rate,
            status="pending"
        )
        db.add(commission)
        
        # Update referrer's earnings
        if not hasattr(referrer, 'member_referral_earnings'):
            referrer.member_referral_earnings = 0
        referrer.member_referral_earnings += commission_amount
        
        db.commit()
        
        return {
            "success": True,
            "commission": commission_amount,
            "rate": commission_rate,
            "commission_id": commission.id,
            "tier": TieredReferralRewards.get_current_tier(referrer)
        }
    
    @staticmethod
    def payout_commission(
        db: Session, 
        commission_id: int, 
        admin_id: int
    ) -> dict:
        """
        Pay out a pending commission.
        
        Returns:
            Dictionary with payout details
        """
        commission = db.query(ReferralCommission).filter(
            ReferralCommission.id == commission_id,
            ReferralCommission.status == "pending"
        ).first()
        
        if not commission:
            return {"success": False, "error": "Commission not found or already paid"}
        
        referrer = db.query(User).filter(User.id == commission.referrer_id).first()
        
        # Update commission
        commission.status = "paid"
        commission.paid_at = datetime.utcnow()
        commission.paid_by = admin_id
        
        # Update referrer's earnings (move from pending to paid)
        if commission.referral_type == "SACCO_REFERRAL":
            referrer.sacco_referral_commission_pending -= commission.amount
            referrer.sacco_referral_commission_paid += commission.amount
        else:
            referrer.member_referral_commission_pending -= commission.amount
            referrer.member_referral_commission_paid += commission.amount
        
        db.commit()
        
        # Create audit log
        create_log(
            db,
            action="REFERRAL_COMMISSION_PAID",
            user_id=admin_id,
            sacco_id=referrer.sacco_id,
            details=f"Paid UGX {commission.amount:,.2f} to {referrer.email} for {commission.referral_type}"
        )
        
        return {
            "success": True,
            "commission_id": commission.id,
            "amount": commission.amount,
            "referrer": referrer.email
        }