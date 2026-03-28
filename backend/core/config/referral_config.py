# backend/config/referral_config.py

class ReferralConfig:
    """Configuration for referral commissions"""
    
    # SACCO-Level Referrals (for platform growth)
    SACCO_REFERRAL_COMMISSION_RATE = 15.0  # 15% of first year subscription
    SACCO_REFERRAL_DURATION = 12  # months (first year only)
    
    # Member-Level Referrals (for SACCO growth)
    MEMBER_REFERRAL_COMMISSION_RATE = 3.0  # 3% of new member's deposits
    MEMBER_REFERRAL_DURATION = 6  # months (first 6 months only)
    
    # Agent-Level Referrals (for marketing team)
    AGENT_REFERRAL_COMMISSION_RATE = 20.0  # 20% of first year subscription
    AGENT_REFERRAL_DURATION = 12  # months
    
    # Commission triggers
    COMMISSION_TRIGGERS = {
        "sacco_subscription": {
            "rate_field": "sacco_referral_commission_rate",
            "duration": 12,
            "one_time": True
        },
        "member_deposit": {
            "rate_field": "member_referral_commission_rate",
            "duration": 6,
            "one_time": False  # Recurring for 6 months
        },
        "loan_interest": {
            "rate_field": "member_referral_commission_rate",
            "duration": 6,
            "one_time": False
        }
    }