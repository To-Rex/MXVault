import datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session as DBSession

from app.config import settings
from app.models.session import Session
from app.models.user import User
from app.utils.crypto import hash_password, verify_password


def authenticate_user(db: DBSession, username: str, password: str) -> User | None:
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_user(
    db: DBSession,
    username: str,
    email: str,
    password: str,
    display_name: str | None = None,
    is_admin: bool = False,
) -> User:
    existing = db.query(User).filter((User.username == username) | (User.email == email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username or email already exists")
    user = User(
        id=str(uuid4()),
        username=username,
        email=email,
        password_hash=hash_password(password),
        display_name=display_name or username,
        is_admin=is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(db: DBSession, user_id: str, **kwargs) -> User | None:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    if "password" in kwargs and kwargs["password"]:
        kwargs["password_hash"] = hash_password(kwargs.pop("password"))
    for key, value in kwargs.items():
        if value is not None and hasattr(user, key):
            setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user


def get_default_admin(db: DBSession) -> User | None:
    return db.query(User).filter(User.is_admin == True).first()


def create_default_admin(db: DBSession) -> User:
    return create_user(
        db=db,
        username="admin",
        email="admin@mxsoft.uz",
        password="admin",
        display_name="Administrator",
        is_admin=True,
    )


def create_session(db: DBSession, user: User, ip_address: str | None = None, user_agent: str | None = None) -> str:
    token = str(uuid4())
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=settings.session_ttl)
    session = Session(
        id=str(uuid4()),
        token=token,
        user_id=user.id,
        username=user.username,
        ip_address=ip_address,
        user_agent=user_agent,
        expires_at=expires_at,
    )
    db.add(session)
    db.commit()
    return token


def get_session_user(token: str, db: DBSession) -> User | None:
    session = db.query(Session).filter(Session.token == token, Session.is_active == True).first()
    if not session:
        return None
    if session.expires_at and session.expires_at < datetime.datetime.utcnow():
        session.is_active = False
        db.commit()
        return None
    session.last_accessed_at = datetime.datetime.utcnow()
    db.commit()
    user = db.query(User).filter(User.id == session.user_id).first()
    return user


def destroy_session(token: str, db: DBSession):
    session = db.query(Session).filter(Session.token == token).first()
    if session:
        session.is_active = False
        db.commit()
