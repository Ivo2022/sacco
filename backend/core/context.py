# core/context.py
from datetime import datetime
from .permissions import get_user_permissions
from .menu_config import MENU_CONFIG

def _serialize_user(user):
    """Convert SQLAlchemy User to dict if needed."""
    if hasattr(user, '__dict__') and not isinstance(user, dict):
        # Simple conversion – adjust to match your serialize_user_full
        return {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": str(user.role).replace("RoleEnum.", ""),
            "sacco_id": user.sacco_id,
            "is_active": user.is_active,
            "is_approved": user.is_approved,
        }
    return user if isinstance(user, dict) else {}

def get_template_context(request, user):
    user_dict = _serialize_user(user)
    
    role_raw: str = ""
    if user_dict:
        role_raw = str(user_dict.get("role", "")).upper().replace("ROLEENUM.", "").replace("_", "")
        print(f"Role raw: {role_raw}")    
    
    if "MANAGER" in role_raw:
        role_key = "MANAGER"
    elif "ACCOUNTANT" in role_raw:
        role_key = "ACCOUNTANT"
    elif "CREDIT_OFFICER" in role_raw or "CREDITOFFICER" in role_raw:
        role_key = "CREDIT_OFFICER"
    elif "MEMBER" in role_raw:
        role_key = "MEMBER"
    elif "SUPER_ADMIN" in role_raw or "SUPERADMIN" in role_raw:
        role_key = "SUPER_ADMIN"
    else:
        role_key = None

    print(f"Role key: {role_key}")
    print(f"Menu config for role: {MENU_CONFIG.get(role_key, [])}")

    return {
        "request": request,
        "user": user_dict,
        "permissions": get_user_permissions(user_dict) if user_dict else [],
        "menu_config": MENU_CONFIG.get(role_key, []),
        "current_path": request.url.path,
        "now": datetime.now()
    }