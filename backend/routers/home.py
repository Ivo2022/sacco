# backend/routers/home.py
"""
Home page router (Render-safe, Jinja2-stable)
"""

from fastapi import Request, Depends, APIRouter
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import List
import logging
from datetime import datetime

from ..core import get_db, get_current_user
from ..models import Sacco, User

logger = logging.getLogger(__name__)

router = APIRouter()


def serialize_sacco(sacco: Sacco) -> dict:
    """Convert Sacco ORM object to safe dict"""
    return {
        "id": sacco.id,
        "name": sacco.name,
        "status": sacco.status,
    }


def serialize_user(user: User) -> dict | None:
    """Convert User ORM object to safe dict"""
    if not user:
        return None

    return {
        "id": user.id,
        "email": user.email,
        "role": str(user.role) if user.role else None,
    }


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Home page showing all SACCOS"""
    try:
        # ✅ Always use templates from app state
        templates = request.app.state.templates

        logger.info(
            f"Rendering index page for user: "
            f"{current_user.email if current_user else 'Anonymous'}"
        )

        # ✅ Fetch data
        saccos: List[Sacco] = db.query(Sacco).order_by(Sacco.name).all()

        # ✅ SERIALIZE (CRITICAL FIX)
        safe_saccos = [serialize_sacco(s) for s in saccos]
        safe_user = serialize_user(current_user)

        # ✅ CLEAN CONTEXT (ONLY SAFE TYPES)
        context = {
            "request": request,   # required by Jinja2Templates
            "saccos": safe_saccos,
            "user": safe_user,
            "show_admin_controls": False,
            "now": datetime.utcnow(),
        }

        # ✅ Render directly (no pre-loading needed)
        return templates.TemplateResponse("index.html", context)

    except Exception as e:
        logger.error(f"Error in index route: {e}", exc_info=True)

        return HTMLResponse(
            content=f"""
            <html>
                <head><title>Error</title></head>
                <body>
                    <h1>Template Error</h1>
                    <p>{str(e)}</p>
                </body>
            </html>
            """,
            status_code=500
        )


# ✅ Lightweight test endpoint (kept simple)
@router.get("/test-template")
async def test_template(request: Request):
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