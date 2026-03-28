# This file makes the routers directory a Python package
# Import routers here for easier access if needed
from . import auth, superadmin, manager, member, accountant, credit_officer, switch_account

__all__ = ['auth', 'superadmin', 'manager', 'member', 'accountant', 'credit_officer', 'switch_account']