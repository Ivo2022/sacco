from datetime import datetime

ROLE_PERMISSIONS = {
    "MANAGER": [
        "view_dashboard", "approve_loans", "manage_members",
        "view_reports", "view_analytics", "manage_staff",
        "view_transactions", "manage_shares", "declare_dividends", "view_logs"
    ],
    "ACCOUNTANT": [
        "view_dashboard", "manage_transactions", "view_reports", "approve_deposits"
    ],
    "CREDIT_OFFICER": [
        "view_dashboard", "manage_loans", "send_reminders", "view_loan_reports"
    ],
    "MEMBER": [
        "view_own_savings", "view_profile", "view_membership_status",  "view_own_shares",  "view_own_dividends"
    ],
    "SUPER_ADMIN": ["*"]
}

def get_user_permissions(user):
    if not user:
        return []
    role = user.get("role", "").upper().replace("ROLEENUM.", "").replace("_", "")
    perms = ROLE_PERMISSIONS.get(role, [])
    return perms