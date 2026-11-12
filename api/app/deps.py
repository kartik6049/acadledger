from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Institute, InstituteStatus, Role, User
from app.security import decode_access_token

COOKIE_NAME = "acadledger_token"


def _token_from(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get(COOKIE_NAME)


_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "X-Requested-With"


def require_csrf_header(request: Request) -> None:
    """Cross-site request forgery guard for the cookie session.

    A page on another site can make a browser send our cookie along with a form
    post, but it cannot add a custom header without our permission. So a request
    that changes something must carry this header, unless it authenticates with
    a Bearer token, which a browser never attaches on its own.
    """
    if request.method in _SAFE_METHODS or "Authorization" in request.headers:
        return
    if CSRF_HEADER not in request.headers:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"Missing {CSRF_HEADER} header on a state-changing request"
        )


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    unauthenticated = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = _token_from(request)
    if not token:
        raise unauthenticated
    user_id = decode_access_token(token)
    if user_id is None:
        raise unauthenticated
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthenticated
    return user


def require_role(*roles: Role) -> Callable[[User], User]:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "You do not have access to this resource"
            )
        return user

    return dependency


def require_active_institute(
    user: User = Depends(require_role(Role.INSTITUTE_ADMIN)), db: Session = Depends(get_db)
) -> Institute:
    """The caller's own institute, which must have been approved by AICTE."""
    institute = db.get(Institute, user.institute_id)
    if institute is None or institute.status != InstituteStatus.ACTIVE:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Your institute is not active yet. An AICTE officer has to approve it first.",
        )
    return institute
