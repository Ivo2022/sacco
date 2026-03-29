# backend/routers/home.py
"""
Home page router
"""
from fastapi import Request, Depends, APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import List
import logging
from pathlib import Path

from ..core import get_db, get_current_user
from ..models import Sacco, User
from ..core.template_helpers import format_money, format_local_time, format_date
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Home page showing all SACCOS"""
    try:
        # Get templates from app state
        templates = request.app.state.templates
        
        # Debug logging
        logger.info(f"Rendering index page for user: {current_user.email if current_user else 'Anonymous'}")
        logger.info(f"Templates object: {templates}")
        logger.info(f"Templates directory: {templates.env.loader.searchpath if hasattr(templates.env.loader, 'searchpath') else 'Unknown'}")
        
        # Get all active SACCOS
        saccos: List[Sacco] = db.query(Sacco).order_by(Sacco.name).all()
        
        # Prepare template context
        context = {
            "request": request,
            "saccos": saccos,
            "user": current_user,
            "show_admin_controls": False,
            "now": datetime.utcnow()
        }
        
        # Try to get template first to catch errors
        try:
            template = templates.get_template("index.html")
            logger.info("Successfully loaded index.html template")
        except Exception as template_error:
            logger.error(f"Failed to load index.html template: {template_error}")
            # Try to list available templates
            if hasattr(templates.env.loader, 'searchpath'):
                template_dir = templates.env.loader.searchpath[0]
                logger.error(f"Template directory: {template_dir}")
                if Path(template_dir).exists():
                    logger.error(f"Available templates: {list(Path(template_dir).glob('*.html'))}")
            raise
        
        # Return template response
        return templates.TemplateResponse("index.html", context)
        
    except Exception as e:
        logger.error(f"Error in index route: {e}", exc_info=True)
        # Return a simple error page instead of crashing
        return HTMLResponse(
            content=f"""
            <html>
                <head><title>Error</title></head>
                <body>
                    <h1>Template Error</h1>
                    <p>Error loading page: {str(e)}</p>
                    <p>Please check the logs for more details.</p>
                </body>
            </html>
            """,
            status_code=500
        )


# Alternative endpoint to test template loading
@router.get("/test-template")
async def test_template(request: Request):
    """Test endpoint to verify template loading"""
    templates = request.app.state.templates
    
    # Try to manually load the template
    try:
        template = templates.get_template("index.html")
        return {
            "status": "success",
            "message": "Template loaded successfully",
            "template_name": "index.html",
            "template_object": str(template)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "template_dirs": templates.env.loader.searchpath if hasattr(templates.env.loader, 'searchpath') else None
        }