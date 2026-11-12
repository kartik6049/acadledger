from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.config import get_settings
from app.db import get_db
from app.deps import COOKIE_NAME, get_current_user
from app.models import User
from app.schemas import LoginRequest, LoginResponse, PasswordChange, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# Password guessing: this many wrong passwords in a row locks the account for a while.
MAX_FAILED_LOGINS = 5
LOCKOUT = timedelta(minutes=15)


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)) -> LoginResponse:
    # locked for update so that parallel guesses cannot each slip under the limit
    user = db.scalar(
        select(User).where(func.lower(User.email) == body.email.lower()).with_for_update()
    )
    now = datetime.now(UTC)
    if user and user.locked_until and user.locked_until > now:
        minutes = int((user.locked_until - now).total_seconds() // 60) + 1
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many failed sign-in attempts. Try again in {minutes} minute(s).",
        )

    # Always run the hash check, even for an unknown email, so both cases take the same time.
    password_ok = verify_password(user.password_hash if user else None, body.password)
    if user is None or not password_ok or not user.is_active:
        if user and not password_ok:
            user.failed_logins += 1
            if user.failed_logins >= MAX_FAILED_LOGINS:
                user.failed_logins = 0
                user.locked_until = now + LOCKOUT
                audit.append(
                    db,
                    action="auth.locked",
                    entity_type="user",
                    entity_id=user.id,
                    institute_id=user.institute_id,
                    payload={"minutes": int(LOCKOUT.total_seconds() // 60)},
                )
            db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

    user.failed_logins = 0
    user.locked_until = None
    settings = get_settings()
    token = create_access_token(user.id, user.role)
    # The browser app authenticates with this cookie; scripts can use the token as a Bearer header.
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.jwt_expire_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )
    audit.append(
        db,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
        actor=user,
        institute_id=user.institute_id,
    )
    db.commit()
    return LoginResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: PasswordChange,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Lets someone replace a password that another person set for them."""
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your current password is not correct")
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a password you have not just used")
    user.password_hash = hash_password(body.new_password)
    audit.append(
        db,
        action="auth.password_changed",
        entity_type="user",
        entity_id=user.id,
        actor=user,
        institute_id=user.institute_id,
    )
    db.commit()
