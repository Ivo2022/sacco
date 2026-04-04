# backend/core/__init__.py
from .database import engine, SessionLocal, get_db, init_db
from .middleware import SACCOStatusMiddleware, TemplateHelpersMiddleware, ActivityTrackingMiddleware
from .dependencies import (
    get_current_user,
    require_auth,
    require_role,
    require_any_role,
    require_manager,
    require_accountant,
    require_credit_officer,
)
from .template_helpers import register_template_helpers
from .config import settings  # Import from config.py

# For backward compatibility, you can also expose commonly used settings directly
from .config import SECRET_KEY, DATABASE_URL, DEBUG
from .context import get_template_context
__all__ = [
    "engine",
    "SessionLocal",
    "get_db",
	"init_db",
    "get_current_user",
    "require_auth",
    "require_role",
    "require_any_role",
    "require_manager",
	"get_template_context",
    "require_accountant",
    "require_credit_officer",
    "settings",
	"SACCOStatusMiddleware",
	"TemplateHelpersMiddleware",
	"ActivityTrackingMiddleware",
	"register_template_helpers",
    "SECRET_KEY",
    "DATABASE_URL",
    "DEBUG",
]