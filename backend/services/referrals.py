# backend/services/referral.py

class ReferralService:
    """Handle all referral-related operations"""
    
    @staticmethod
    def generate_sacco_referral_code(user: User) -> str:
        """Generate unique referral code for SACCO-level referrals"""
        import uuid
        code = f"SACCOREF_{user.id}_{uuid.uuid4().hex[:8]}"
        user.sacco_referral_code = code
        return code
    
    @staticmethod
    def generate_member_referral_code(user: User) -> str:
        """Generate unique referral code for member-level referrals"""
        import uuid
        code = f"MEMBERREF_{user.id}_{uuid.uuid4().hex[:8]}"
        user.member_referral_code = code
        return code
    
    @staticmethod
    def apply_sacco_referral(db: Session, sacco: Sacco, referral_code: str, referrer: User):
        """Apply referral when a new SACCO is created"""
        
        # Validate code type
        if not referral_code.startswith("SACCOREF_"):
            return None
        
        # Find referrer by code
        referrer = db.query(User).filter(User.sacco_referral_code == referral_code).first()
        if not referrer:
            return None
        
        # Link SACCO to referrer
        sacco.referred_by_id = referrer.id
        
        # Calculate commission (e.g., 15% of first year subscription)
        # Assuming subscription fee of UGX 100,000/year
        subscription_fee = 100000
        commission = (subscription_fee * referrer.sacco_referral_commission_rate) / 100
        
        # Create commission record
        commission_record = ReferralCommission(
            referrer_id=referrer.id,
            referred_entity_type="sacco",
            referred_entity_id=sacco.id,
            referral_type="SACCO_REFERRAL",
            source="sacco_subscription",
            amount=commission,
            percentage=referrer.sacco_referral_commission_rate,
            status="pending"
        )
        db.add(commission_record)
        
        # Update referrer's earnings
        referrer.sacco_referral_earnings += commission
        referrer.sacco_referral_commission_pending += commission
        
        db.commit()
        
        # Create audit log
        create_log(
            db,
            action="SACCO_REFERRAL_APPLIED",
            user_id=referrer.id,
            sacco_id=sacco.id,
            details=f"Referral commission UGX {commission:,.2f} for SACCO {sacco.name}"
        )
        
        return commission_record
    
    @staticmethod
    def apply_member_referral(db: Session, new_member: User, referral_code: str):
        """Apply referral when a new member joins a SACCO"""
        
        # Validate code type
        if not referral_code.startswith("MEMBERREF_"):
            return None
        
        # Find referrer by code
        referrer = db.query(User).filter(User.member_referral_code == referral_code).first()
        if not referrer:
            return None
        
        # Ensure they are in the same SACCO
        if referrer.sacco_id != new_member.sacco_id:
            return None
        
        # Link member to referrer
        new_member.referred_by_id = referrer.id
        
        # Update referrer's statistics
        referrer.total_referrals += 1
        
        db.commit()
        
        return referrer
    
    @staticmethod
    def process_member_deposit_commission(db: Session, member: User, deposit_amount: float, deposit_id: int):
        """Process commission when a referred member makes a deposit"""
        
        if not member.referred_by_id:
            return None
        
        referrer = db.query(User).filter(User.id == member.referred_by_id).first()
        if not referrer:
            return None
        
        # Calculate commission (e.g., 3% of deposit)
        commission = (deposit_amount * referrer.member_referral_commission_rate) / 100
        
        commission_record = ReferralCommission(
            referrer_id=referrer.id,
            referred_entity_type="member",
            referred_entity_id=member.id,
            referral_type="MEMBER_REFERRAL",
            source="member_deposit",
            source_id=deposit_id,
            amount=commission,
            percentage=referrer.member_referral_commission_rate,
            status="pending"
        )
        db.add(commission_record)
        
        referrer.member_referral_earnings += commission
        referrer.member_referral_commission_pending += commission
        
        db.commit()
        
        return commission_record