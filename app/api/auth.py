from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.auth import authenticate_user, create_session, destroy_session, get_session_user
from app.services.audit import log_audit
from app.templates import templates

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login_page(request: Request):
    token = request.cookies.get("session_token")
    if token:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse(request, "auth/login.html", {"request": request})


@router.post("/login")
def login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, username, password)
    if not user:
        log_audit(db, action="login_failed", username=username, status="failed", ip_address=request.client.host if request.client else None)
        return templates.TemplateResponse(request, "auth/login.html", {"request": request, "error": "Invalid username or password"})

    token = create_session(db, user, ip_address=request.client.host if request.client else None)
    user.last_login_at = __import__("datetime").datetime.now()
    db.commit()

    log_audit(db, action="login", user_id=user.id, username=user.username, ip_address=request.client.host if request.client else None)

    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(key="session_token", value=token, httponly=True, max_age=86400, samesite="lax", secure=False)
    return response


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get("session_token")
    if token:
        destroy_session(token, db)
    response = RedirectResponse(url="/auth/login", status_code=302)
    response.delete_cookie("session_token")
    return response


@router.get("/profile")
def profile_page(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request, "auth/profile.html", {"request": request, "user": user})


@router.post("/profile")
def update_profile(
    request: Request,
    display_name: str = Form(None),
    email: str = Form(None),
    current_password: str = Form(None),
    new_password: str = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.services.auth import update_user, verify_password
    from app.utils.crypto import hash_password

    if current_password and new_password:
        if not verify_password(current_password, user.password_hash):
            return templates.TemplateResponse(request, "auth/profile.html", {"request": request, "user": user, "error": "Current password is incorrect"})
        user.password_hash = hash_password(new_password)

    if display_name:
        user.display_name = display_name
    if email:
        user.email = email

    db.commit()
    log_audit(db, action="profile_update", user_id=user.id, username=user.username)

    return templates.TemplateResponse(request, "auth/profile.html", {"request": request, "user": user, "success": "Profile updated"})
