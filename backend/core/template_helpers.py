from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from jinja2 import Environment

from .config import settings

# Timezone setup
LOCAL_OFFSET = timedelta(hours=settings.LOCAL_OFFSET_HOURS)
LOCAL_TZ = timezone(LOCAL_OFFSET, name=settings.TIMEZONE_NAME)

def format_local_time(value: Any) -> str:
    """Convert UTC datetime to local timezone"""
    if value is None:
        return ''
    
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except:
            try:
                value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f')
            except:
                try:
                    value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                except:
                    return value
    
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    
    local_value = value.astimezone(LOCAL_TZ)
    return local_value.strftime('%Y-%m-%d %H:%M:%S')

def format_money(value: Any) -> str:
    """Format money with thousand separators and 2 decimal places"""
    if value is None:
        return 'UGX 0.00'
    
    try:
        amount = float(value)
        formatted = f"{amount:,.2f}"
        return f"UGX {formatted}"
    except (ValueError, TypeError):
        return 'UGX 0.00'

def format_date(value: Any, format_str: str = '%Y-%m-%d') -> str:
    """Format datetime to date string"""
    if value is None:
        return ''
    if hasattr(value, 'strftime'):
        return value.strftime(format_str)
    return str(value)

def format_datetime(value: Any, format_str: str = '%Y-%m-%d %H:%M:%S') -> str:
    """Format datetime to string"""
    if value is None:
        return ''
    if hasattr(value, 'strftime'):
        return value.strftime(format_str)
    return str(value)

def format_percentage(value: Any, decimals: int = 2) -> str:
    """Format percentage"""
    if value is None:
        return '0%'
    try:
        return f"{float(value):.{decimals}f}%"
    except (ValueError, TypeError):
        return '0%'

def register_template_helpers(templates: Environment) -> None:
    """Register all helper functions with Jinja2 templates"""
    templates.env.globals.update({
        'money': format_money,
        'local_time': format_local_time,
        'date': format_date,
        'datetime': format_datetime,
        'percentage': format_percentage,
        'now': datetime.utcnow
    })
    
    # Register as filters as well
    templates.env.filters.update({
        'money': format_money,
        'local_time': format_local_time,
        'date': format_date,
        'datetime': format_datetime,
        'percentage': format_percentage,
    })

def get_current_tier(user) -> dict:
    """Get current tier info for template (imported from referral service)"""
    from ..services.referral_service import TieredReferralRewards
    if user:
        return TieredReferralRewards.get_current_tier(user)
    return {"description": "Bronze", "rate": 3.0}