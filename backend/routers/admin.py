
from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from ..core.dependencies import  get_current_user
from ..models import User, RoleEnum

# from ..session_auth import get_current_user
from ..core.database import get_db

router = APIRouter()
templates = Jinja2Templates(directory="backend/templates")


@router.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request, user: User = Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access only")
    conn = get_db()
    total_savings = conn.execute("SELECT COALESCE(SUM(amount),0) FROM savings WHERE type = 'deposit'").fetchone()[0]
    total_withdrawals = conn.execute("SELECT COALESCE(SUM(amount),0) FROM savings WHERE type = 'withdraw'").fetchone()[0]
    total_loans = conn.execute("SELECT COALESCE(SUM(amount),0) FROM loans").fetchone()[0]
    conn.close()
    try:
        net_savings = float(total_savings) - float(total_withdrawals)
    except Exception:
        net_savings = 0.0
    return templates.TemplateResponse("admin/dashboard.html", {"request": request, "user": user, "show_admin_controls": True, "net_savings": net_savings, "total_loans": total_loans})


@router.get("/admin/users", response_class=HTMLResponse)
def list_users(request: Request, user: User = Depends(get_current_user)):
    #if not user.is_admin:
    if user.role != RoleEnum.SACCO_ADMIN:
        raise HTTPException(status_code=403, detail="Admins only")
    conn = get_db()
    users = conn.execute("SELECT id, username, is_admin FROM users").fetchall()
    conn.close()
    return templates.TemplateResponse("admin/users.html", {"request": request, "users": users, "user": user, "show_admin_controls": True})


@router.post("/admin/toggle-role")
def toggle_user_role(request: Request, user_id: int = Form(...), current_user: User = Depends(get_current_user)):
    # if not current_user.get("is_admin"):
    if current_user.role != RoleEnum.SACCO_ADMIN:
        raise HTTPException(status_code=403)
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user:
        new_role = 0 if user["is_admin"] else 1
        conn.execute("UPDATE users SET is_admin = ? WHERE id = ?", (new_role, user_id))
        conn.commit()
    conn.close()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/delete-user")
def delete_user(request: Request, user_id: int = Form(...), current_user: User = Depends(get_current_user)):
    if current_user.role != RoleEnum.SACCO_ADMIN:
        raise HTTPException(status_code=403)
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself.")
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/admin/loans", response_class=HTMLResponse)
def admin_view_loans(request: Request, user: User = Depends(get_current_user)):
    if user.role != RoleEnum.SACCO_ADMIN:
        raise HTTPException(status_code=403, detail="Admins only")
    conn = get_db()
    loans = conn.execute("SELECT loans.id, users.username, loans.amount, loans.term, loans.status, loans.timestamp FROM loans JOIN users ON loans.user_id = users.id ORDER BY loans.timestamp DESC").fetchall()
    conn.close()
    return templates.TemplateResponse("admin/loans.html", {"request": request, "user": user, "loans": loans, "show_admin_controls": True})


@router.post("/admin/loan/approve")
def approve_loan(request: Request, loan_id: int = Form(...), current_user: User = Depends(get_current_user)):
    if current_user.role != RoleEnum.SACCO_ADMIN:
        raise HTTPException(status_code=403)
    conn = get_db()
    conn.execute("UPDATE loans SET status = 'approved' WHERE id = ?", (loan_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/admin/loans", status_code=303)


@router.post("/admin/loan/reject")
def reject_loan(request: Request, loan_id: int = Form(...), current_user: User = Depends(get_current_user)):
    if current_user.role != RoleEnum.SACCO_ADMIN:
        raise HTTPException(status_code=403)
    conn = get_db()
    conn.execute("UPDATE loans SET status = 'rejected' WHERE id = ?", (loan_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/admin/loans", status_code=303)


@router.get("/admin/reports", response_class=HTMLResponse)
def admin_reports(request: Request, user: User = Depends(get_current_user)):
    if user.role != RoleEnum.SACCO_ADMIN:
        raise HTTPException(status_code=403, detail="Admins only")
    conn = get_db()
    total_deposits = conn.execute("SELECT COALESCE(SUM(amount),0) FROM savings WHERE type = 'deposit'").fetchone()[0]
    total_withdrawals = conn.execute("SELECT COALESCE(SUM(amount),0) FROM savings WHERE type = 'withdraw'").fetchone()[0]
    total_loans = conn.execute("SELECT COALESCE(SUM(amount),0) FROM loans").fetchone()[0]
    outstanding_loans = conn.execute("SELECT COALESCE(SUM(amount),0) FROM loans WHERE status = 'approved'").fetchone()[0]
    conn.close()
    try:
        net_savings = float(total_deposits) - float(total_withdrawals)
    except Exception:
        net_savings = 0.0
    try:
        total_loans = float(total_loans)
    except Exception:
        total_loans = 0.0
    try:
        outstanding_loans = float(outstanding_loans)
    except Exception:
        outstanding_loans = 0.0
    return templates.TemplateResponse("admin/reports.html", {"request": request, "user": user, "report": {"net_savings": net_savings, "total_loans": total_loans, "outstanding_loans": outstanding_loans}, "show_admin_controls": True})


@router.get("/admin/logs", response_class=HTMLResponse)
def view_logs(request: Request, user: User = Depends(get_current_user)):
    if user.role != RoleEnum.SACCO_ADMIN:
        raise HTTPException(status_code=403, detail="Access denied")
    conn = get_db()
    logs = conn.execute("""
        SELECT logs.id, users.username, logs.action, logs.timestamp
        FROM logs
        JOIN users ON logs.user_id = users.id
        ORDER BY logs.timestamp DESC
    """).fetchall()
    conn.close()
    return templates.TemplateResponse("admin/logs.html", {"request": request, "user": user, "logs": logs, "show_admin_controls": True})
