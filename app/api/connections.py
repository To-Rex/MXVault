from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.connection import PGConnection
from app.models.user import User
from app.services.audit import log_audit
from app.services.connection import create_connection, delete_connection, test_connection, update_connection
from app.templates import templates

router = APIRouter(prefix="/connections", tags=["connections"])


@router.get("")
def list_connections(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    connections = db.query(PGConnection).order_by(PGConnection.created_at.desc()).all()
    return templates.TemplateResponse(request, "connections/list.html", {"request": request, "user": user, "connections": connections})


@router.get("/new")
def new_connection(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request, "connections/form.html", {"request": request, "user": user})


@router.post("/new")
def create_connection_route(
    request: Request,
    name: str = Form(...),
    host: str = Form(...),
    port: int = Form(5432),
    database: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    ssl_mode: str = Form("prefer"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        conn = create_connection(db, name, host, port, database, username, password, ssl_mode)
        log_audit(db, action="connection_created", user_id=user.id, username=user.username,
                  resource_type="connection", resource_id=conn.id, details=f"Connection '{name}' created")
        return RedirectResponse(url="/connections", status_code=302)
    except Exception as e:
        return templates.TemplateResponse(request, "connections/form.html", {"request": request, "user": user, "error": str(e)})


@router.get("/{connection_id}")
def view_connection(connection_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conn = db.query(PGConnection).filter(PGConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return templates.TemplateResponse(request, "connections/view.html", {"request": request, "user": user, "connection": conn})


@router.get("/{connection_id}/edit")
def edit_connection_form(connection_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conn = db.query(PGConnection).filter(PGConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return templates.TemplateResponse(request, "connections/form.html", {"request": request, "user": user, "connection": conn})


@router.post("/{connection_id}/edit")
def update_connection_route(
    connection_id: str,
    request: Request,
    name: str = Form(None),
    host: str = Form(None),
    port: int = Form(None),
    database: str = Form(None),
    username: str = Form(None),
    password: str = Form(None),
    ssl_mode: str = Form(None),
    is_active: bool = Form(True),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conn = update_connection(db, connection_id, name=name, host=host, port=port,
                              database=database, username=username, password=password or None,
                              ssl_mode=ssl_mode, is_active=is_active)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    log_audit(db, action="connection_updated", user_id=user.id, username=user.username,
              resource_type="connection", resource_id=conn.id)
    return RedirectResponse(url="/connections", status_code=302)


@router.post("/{connection_id}/delete")
def delete_connection_route(connection_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conn = db.query(PGConnection).filter(PGConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    name = conn.name
    delete_connection(db, connection_id)
    log_audit(db, action="connection_deleted", user_id=user.id, username=user.username,
              resource_type="connection", resource_id=connection_id, details=f"Connection '{name}' deleted")
    return RedirectResponse(url="/connections", status_code=302)


@router.post("/{connection_id}/test")
def test_connection_route(connection_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conn = db.query(PGConnection).filter(PGConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    result = test_connection(conn)
    conn.last_tested_at = __import__("datetime").datetime.now()
    db.commit()
    log_audit(db, action="connection_tested", user_id=user.id, username=user.username,
              resource_type="connection", resource_id=connection_id, details=str(result["success"]))
    return result
