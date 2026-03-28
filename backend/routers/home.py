"""
Home page router
"""
from fastapi import Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import List

from ..core import get_db, get_current_user
from ..models import Sacco, User
from ..core.template_helpers import format_money, format_local_time, format_date
from datetime import datetime

templates = Jinja2Templates(directory="backend/templates")

from fastapi import APIRouter
router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Home page showing all SACCOS"""
    # Get all active SACCOS
    saccos: List[Sacco] = db.query(Sacco).order_by(Sacco.name).all()
    
    # Prepare template context
    context = {
        "request": request,
        "saccos": saccos,
        "user": current_user,
        "show_admin_controls": False,
        "now": datetime.utcnow(),
        # Add helper functions directly for this template
        "money": format_money,
        "local_time": format_local_time,
        "date": format_date
    }
    
    return templates.TemplateResponse("index.html", context)