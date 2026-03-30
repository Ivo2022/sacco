# backend/routers/home.py
"""
Home page router (Render-safe, Jinja2-stable)
"""

from fastapi import Request, Depends, APIRouter
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import logging
from datetime import datetime

from ..core import get_db, get_current_user
from ..models import Sacco, User
logger = logging.getLogger(__name__)

router = APIRouter()


def serialize_sacco(sacco: Sacco) -> Dict[str, Any]:
    """Convert Sacco ORM object to safe dict for templates"""
    return {
        "id": sacco.id,
        "name": sacco.name,
        "status": sacco.status,
        "email": sacco.email,
        "phone": sacco.phone,
        "website": sacco.website,
        "address": sacco.address,
        "registration_no": sacco.registration_no,
        "created_at": sacco.created_at.isoformat() if sacco.created_at is not None else None,
    }


def serialize_user(user: User) -> Dict[str, Any] | None:
    """Convert User ORM object to safe dict for templates"""
    if not user:
        return None
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.value if hasattr(user.role, 'value') else str(user.role).split('.')[-1] if user.role else None,
        "is_admin": user.is_admin,
        "dashboard_url": user.get_dashboard_url,
        "sacco_id": user.sacco_id,
        "linked_member_account_id": user.linked_member_account_id,
        "linked_admin_id": user.linked_admin_id,
    }


@router.head("/", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Render home page with all SACCOS"""
    try:
        templates = request.app.state.templates
        logger.info(f"Rendering index for user: {current_user.email if current_user else 'Anonymous'}")

        # Fetch data
        saccos: List[Sacco] = db.query(Sacco).order_by(Sacco.name).all()

        # Serialize ORM objects safely
        safe_saccos = [serialize_sacco(s) for s in saccos]
        sacco_dict = {s["id"]: s for s in safe_saccos}
        safe_user = serialize_user(current_user)

        # Build context for Jinja2 (no ORM objects, only dicts, lists, strings, numbers)

        context = {
            "request": request,
            "saccos": sacco_dict,
            "user": safe_user,
            "show_admin_controls": safe_user["is_admin"] if safe_user else False,
            "now": datetime.utcnow(),
            "error": None,
            "message": None,
	    }

        return templates.TemplateResponse("index.html", context)

    except Exception as e:
        logger.error(f"Error in index route: {e}", exc_info=True)
        return HTMLResponse(
            content=f"""
            <html>
                <head><title>Template Error</title></head>
                <body>
                    <h1>Template Error</h1>
                    <p>{str(e)}</p>
                    <p>Check the logs for more details.</p>
                </body>
            </html>
            """,
            status_code=500
        )


@router.get("/test-template")
async def test_template(request: Request):
    """Test template loading"""
    templates = request.app.state.templates
    try:
        template = templates.get_template("index.html")
        return {
            "status": "success",
            "template": "index.html",
            "loader_paths": getattr(templates.env.loader, "searchpath", []),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }