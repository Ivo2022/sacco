from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
import logging
from typing import List

from sqlalchemy.orm import Session
from datetime import datetime

logger = logging.getLogger(__name__)
from .config import settings
from .database import get_db_session

logger = logging.getLogger(__name__)

class SACCOStatusMiddleware(BaseHTTPMiddleware):
    """Middleware to check if user's SACCO is active"""
    
    # Public paths that don't require SACCO status check
    PUBLIC_PATHS: List[str] = [
        '/', '/login', '/logout', '/register', 
        '/static', '/auth', '/debug', '/docs', 
        '/redoc', '/openapi.json'
    ]
    
    async def dispatch(self, request: Request, call_next):
        # Skip for public routes
        if any(request.url.path.startswith(path) for path in self.PUBLIC_PATHS):
            return await call_next(request)
        
        # Check if user is logged in
        user_id = request.session.get("user_id")
        if not user_id:
            return await call_next(request)
        
        # Check SACCO status
        from ..models import User, Sacco
        
        db = get_db_session()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user and user.sacco_id:
                sacco = db.query(Sacco).filter(Sacco.id == user.sacco_id).first()
                
                # Check if SACCO is inactive or suspended
                if sacco and sacco.status in ['inactive', 'suspended']:
                    # Clear session and redirect to login with message
                    request.session.clear()
                    request.session["flash_message"] = f"Your SACCO '{sacco.name}' is currently {sacco.status}. Please contact the administrator."
                    request.session["flash_type"] = "danger"
                    return RedirectResponse(url="/login", status_code=303)
        finally:
            db.close()
        
        return await call_next(request)


class TemplateHelpersMiddleware(BaseHTTPMiddleware):
    """Middleware to add helper functions to request state for templates"""
    
    async def dispatch(self, request: Request, call_next):
        # Import helper functions here to avoid circular imports
        from .template_helpers import format_money, format_local_time, format_date
        
        # Add helper functions to request state
        request.state.money = format_money
        request.state.local_time = format_local_time
        request.state.date = format_date
        
        response = await call_next(request)
        return response
		
# backend/core/middleware.py
class ActivityTrackingMiddleware(BaseHTTPMiddleware):
    """Middleware to track user activity on each request"""
    
    async def dispatch(self, request: Request, call_next):
        # Process the request first
        response = await call_next(request)
        
        # Update user activity after request (so we don't slow down the response)
        try:
            # Get user from session
            user_id = request.session.get("user_id")
            if user_id:
                # Get database session
                db = request.app.state.db_session() if hasattr(request.app.state, 'db_session') else None
                
                if db:
                    from ..models import User
                    user = db.query(User).filter(User.id == user_id).first()
                    if user:
                        # Update last activity
                        user.last_activity = datetime.utcnow()
                        db.commit()
                        logger.debug(f"Updated last_activity for user {user_id}")
                    db.close()
        except Exception as e:
            # Don't let activity tracking errors affect the response
            logger.error(f"Error updating last_activity: {e}")
        
        return response