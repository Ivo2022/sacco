# menu_config.py
MENU_CONFIG = {
    "MANAGER": [
        {
            "section": "Dashboard",
            "items": [
                {"name": "Main Dashboard", "url": "/manager/dashboard", "permission": "view_dashboard", "icon": "bi-speedometer2"}
            ]
        },
        {
            "section": "Pending",
            "items": [
                {"name": "All Pending", "url": "/manager/pending/all", "permission": "approve_loans", "icon": "bi-hourglass-split"},
                {"name": "Members", "url": "/manager/pending-members", "permission": "manage_members", "icon": "bi-person-plus"},
                {"name": "Loans", "url": "/manager/loans/pending", "permission": "approve_loans", "icon": "bi-cash-stack"},
                {"name": "Deposits", "url": "/manager/deposits/pending", "permission": "approve_deposits", "icon": "bi-bank"}
            ]
        },
        {
            "section": "Members",
            "items": [
                {"name": "All Members", "url": "/manager/members", "permission": "manage_members", "icon": "bi-people"},
                {"name": "Applications", "url": "/manager/membership/applications", "permission": "manage_members", "icon": "bi-file-earmark-check"}
            ]
        },
        {
            "section": "Staff",
            "items": [
                {"name": "Manage Staff", "url": "/manager/staff", "permission": "manage_staff", "icon": "bi-person-badge"},
                {"name": "Activity", "url": "/manager/staff-activity", "permission": "manage_staff", "icon": "bi-activity"}
            ]
        },
        {
            "section": "Finance",
            "items": [
                {"name": "Transactions", "url": "/manager/all-transactions", "permission": "view_transactions", "icon": "bi-receipt"},
                {"name": "Loans", "url": "/manager/all-loans", "permission": "approve_loans", "icon": "bi-calculator"},
                {"name": "Reports", "url": "/manager/reports", "permission": "view_reports", "icon": "bi-file-text"}
            ]
        },
        {
            "section": "Shares",
            "items": [
                {"name": "Types", "url": "/manager/shares/types", "permission": "manage_shares", "icon": "bi-tags"},
                {"name": "Holdings", "url": "/manager/shares/holdings", "permission": "manage_shares", "icon": "bi-pie-chart"},
                {"name": "Dividends", "url": "/manager/dividends/declare", "permission": "declare_dividends", "icon": "bi-gift"}
            ]
        },
        {
            "section": "Analytics",
            "items": [
                {"name": "Loan Risk", "url": "/manager/loan-risk-dashboard", "permission": "view_analytics", "icon": "bi-graph-up"},
                {"name": "Insights", "url": "/manager/insights/dashboard", "permission": "view_analytics", "icon": "bi-lightbulb"}
            ]
        },
        {
            "section": "System",
            "items": [
                {"name": "Logs", "url": "/manager/logs", "permission": "view_logs", "icon": "bi-journal"},
                {"name": "Export", "url": "/manager/reports", "permission": "view_reports", "icon": "bi-download"}
            ]
        }
    ],
    "ACCOUNTANT": [
        {
            "section": "Dashboard",
            "items": [
                {"name": "Dashboard", "url": "/accountant/dashboard", "permission": "view_dashboard", "icon": "bi-speedometer2"}
            ]
        },
        {
            "section": "Transactions",
            "items": [
                {"name": "Pending Deposits", "url": "/accountant/deposits/pending", "permission": "approve_deposits", "icon": "bi-clock-history"},
                {"name": "All Transactions", "url": "/accountant/transactions", "permission": "manage_transactions", "icon": "bi-receipt"},
                {"name": "Savings Overview", "url": "/accountant/savings", "permission": "manage_transactions", "icon": "bi-piggy-bank"}
            ]
        },
        {
            "section": "Reports",
            "items": [
                {"name": "Financial Reports", "url": "/accountant/reports", "permission": "view_reports", "icon": "bi-file-text"}
            ]
        }
    ],
    "CREDIT_OFFICER": [
        {
            "section": "Dashboard",
            "items": [
                {"name": "Dashboard", "url": "/credit-officer/dashboard", "permission": "view_dashboard", "icon": "bi-speedometer2"}
            ]
        },
        {
            "section": "Loans",
            "items": [
                {"name": "All Loans", "url": "/credit-officer/loans", "permission": "manage_loans", "icon": "bi-cash-stack"},
                {"name": "Send Reminders", "url": "/credit-officer/reminders", "permission": "send_reminders", "icon": "bi-bell"},
                {"name": "Loan Reports", "url": "/credit-officer/reports", "permission": "view_loan_reports", "icon": "bi-file-text"},
                {"name": "Analytics", "url": "/credit-officer/analytics", "permission": "manage_loans", "icon": "bi-graph-up"}
            ]
        }
    ],
    "MEMBER": [
        {
            "section": "My Accounts",
            "icon": "bi-person",
            "items": [
                {"name": "Dashboard", "url": "/member/dashboard", "permission": "view_dashboard", "icon": "bi-speedometer2"},
                {"name": "My Savings", "url": "/member/savings", "permission": "view_own_savings", "icon": "bi-piggy-bank"},
                {"name": "My Shares", "url": "/member/shares", "permission": "view_own_shares", "icon": "bi-pie-chart"}, 
                {"name": "My Dividends", "url": "/member/dividends", "permission": "view_own_dividends", "icon": "bi-gift"},
                {"name": "Membership Status", "url": "/membership/status", "permission": "view_membership_status", "icon": "bi-person-check"},
            ]
        }
    ],
    "SUPER_ADMIN": [
        {
            "section": "Platform",
            "items": [
                {"name": "Dashboard", "url": "/superadmin/dashboard", "permission": "*", "icon": "bi-speedometer2"},
                {"name": "Manage SACCOs", "url": "/superadmin/saccos", "permission": "*", "icon": "bi-building"},
                {"name": "All Managers", "url": "/superadmin/managers", "permission": "*", "icon": "bi-person-badge"},
                {"name": "All Staff", "url": "/superadmin/staff", "permission": "*", "icon": "bi-people"},
                {"name": "System Logs", "url": "/superadmin/logs", "permission": "*", "icon": "bi-file-text"},
                {"name": "Insights Dashboard", "url": "/superadmin/insights/dashboard", "permission": "*", "icon": "bi-lightbulb"}
            ]
        }
    ]
}