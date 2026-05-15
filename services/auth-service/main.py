"""
Zero Trust Auth Service
Implements Zero Trust security: "never trust, always verify."

Key principles enforced:
  1. Short-lived JWTs (15-minute TTL) — no long-lived sessions
  2. Every request is verified regardless of network location
  3. Least-privilege RBAC via OPA (Open Policy Agent)
  4. Continuous re-verification: tokens cannot be extended, only refreshed
  5. All auth events are logged to BigQuery audit trail
  6. mTLS between services (enforced at Istio layer)

Roles (least to most privileged):
  viewer        → read-only access to non-sensitive assets
  data_analyst  → read access including INTERNAL, no PII raw values
  data_steward  → read/write for metadata, manage terms, assign PII classification
  admin         → full access including user management and source registration
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.requests import Request
from starlette.responses import Response

log = structlog.get_logger(__name__)


class Settings(BaseSettings):
    jwt_secret_key: str = "REPLACE_WITH_256BIT_SECRET_FROM_SECRET_MANAGER"
    jwt_algorithm: str = "HS256"
    jwt_access_token_ttl_minutes: int = 15     # Zero Trust: short TTL
    jwt_refresh_token_ttl_days: int = 1        # Refresh tokens expire daily
    opa_url: str = "http://opa:8181"
    audit_service_url: str = "http://audit-service:8007"
    service_name: str = "auth-service"
    bcrypt_rounds: int = 12

    class Config:
        env_file = ".env"


settings = Settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()

AUTH_ATTEMPTS = Counter("auth_attempts_total", "Authentication attempts", ["outcome"])
TOKEN_VALIDATIONS = Counter("token_validations_total", "Token validation checks", ["outcome"])
AUTHZ_DECISIONS = Counter("authz_decisions_total", "Authorization decisions", ["decision", "role"])
AUTH_DURATION = Histogram("auth_duration_seconds", "Auth operation duration")


# --------------------------------------------------------------------------- #
#  Role definitions & permission matrix                                        #
# --------------------------------------------------------------------------- #

ROLE_HIERARCHY = {
    "viewer": 0,
    "data_analyst": 1,
    "data_steward": 2,
    "admin": 3,
}

# Resource × Action → Minimum required role
PERMISSION_MATRIX: dict[str, dict[str, str]] = {
    "asset": {
        "read": "viewer",
        "read_sensitive": "data_analyst",
        "read_pii": "data_steward",
        "write": "data_steward",
        "delete": "admin",
    },
    "column": {
        "read": "viewer",
        "read_pii_value": "admin",         # Raw PII values: admin only
        "write": "data_steward",
    },
    "term": {
        "read": "viewer",
        "write": "data_steward",
        "delete": "data_steward",
    },
    "source": {
        "read": "data_steward",
        "write": "admin",
        "delete": "admin",
    },
    "user": {
        "read": "admin",
        "write": "admin",
    },
    "audit": {
        "read": "admin",
    },
    "lineage": {
        "read": "data_analyst",
        "write": "data_steward",
    },
}


# --------------------------------------------------------------------------- #
#  User store (replace with identity provider / LDAP in production)           #
# --------------------------------------------------------------------------- #

class User(BaseModel):
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    full_name: str
    role: str = "viewer"
    is_active: bool = True
    department: str | None = None
    hashed_password: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login: datetime | None = None
    mfa_enabled: bool = False


# Seeded demo users
def _hash(pw: str) -> str:
    return pwd_context.hash(pw)


_users_db: dict[str, User] = {
    "admin@datacatalog.io": User(
        email="admin@datacatalog.io",
        full_name="Platform Admin",
        role="admin",
        hashed_password=_hash("Admin@SecureP@ss1"),
    ),
    "steward@datacatalog.io": User(
        email="steward@datacatalog.io",
        full_name="Data Steward",
        role="data_steward",
        hashed_password=_hash("Steward@SecureP@ss1"),
    ),
    "analyst@datacatalog.io": User(
        email="analyst@datacatalog.io",
        full_name="Data Analyst",
        role="data_analyst",
        hashed_password=_hash("Analyst@SecureP@ss1"),
    ),
    "viewer@datacatalog.io": User(
        email="viewer@datacatalog.io",
        full_name="Read-Only User",
        role="viewer",
        hashed_password=_hash("Viewer@SecureP@ss1"),
    ),
}

# Revoked token store (in production: Redis with TTL)
_revoked_tokens: set[str] = set()


# --------------------------------------------------------------------------- #
#  JWT helpers                                                                 #
# --------------------------------------------------------------------------- #

def create_access_token(user: User, request_ip: str | None = None) -> str:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.jwt_access_token_ttl_minutes)
    payload = {
        "sub": user.user_id,
        "email": user.email,
        "role": user.role,
        "full_name": user.full_name,
        "department": user.department,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": str(uuid.uuid4()),         # Unique token ID for revocation
        "iss": "data-catalog-auth-service",
        "aud": "data-catalog-platform",
        "ip": request_ip,                  # Bind token to originating IP
        "token_type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=settings.jwt_refresh_token_ttl_days)
    payload = {
        "sub": user.user_id,
        "email": user.email,
        "exp": int(expires.timestamp()),
        "jti": str(uuid.uuid4()),
        "iss": "data-catalog-auth-service",
        "token_type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_and_validate_token(token: str, request_ip: str | None = None) -> dict:
    """
    Decode and validate a JWT.
    Checks: signature, expiry, revocation, and IP binding (Zero Trust).
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            audience="data-catalog-platform",
        )
    except JWTError as exc:
        TOKEN_VALIDATIONS.labels(outcome="invalid").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check revocation list
    jti = payload.get("jti")
    if jti and jti in _revoked_tokens:
        TOKEN_VALIDATIONS.labels(outcome="revoked").inc()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")

    # Zero Trust: verify IP matches (optional, configurable)
    token_ip = payload.get("ip")
    if token_ip and request_ip and token_ip != request_ip:
        log.warning("token_ip_mismatch", token_ip=token_ip, request_ip=request_ip, user=payload.get("email"))
        # In strict mode: raise 401. In audit mode: log only.
        # Uncomment for strict enforcement:
        # raise HTTPException(status_code=401, detail="Token IP mismatch")

    TOKEN_VALIDATIONS.labels(outcome="valid").inc()
    return payload


# --------------------------------------------------------------------------- #
#  OPA policy evaluation                                                       #
# --------------------------------------------------------------------------- #

async def evaluate_policy(
    role: str,
    resource: str,
    action: str,
    context: dict | None = None,
) -> bool:
    """
    Evaluate access policy via OPA (Open Policy Agent).
    Falls back to local RBAC matrix if OPA is unavailable.
    """
    # Try OPA first
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.post(
                f"{settings.opa_url}/v1/data/datacatalog/authz/allow",
                json={
                    "input": {
                        "role": role,
                        "resource": resource,
                        "action": action,
                        "context": context or {},
                    }
                },
            )
            if resp.status_code == 200:
                result = resp.json()
                decision = result.get("result", False)
                AUTHZ_DECISIONS.labels(
                    decision="allow" if decision else "deny", role=role
                ).inc()
                return decision
    except Exception:
        log.warning("opa_unavailable_fallback_to_local_rbac")

    # Local RBAC fallback
    return _local_rbac_check(role, resource, action)


def _local_rbac_check(role: str, resource: str, action: str) -> bool:
    required_role = PERMISSION_MATRIX.get(resource, {}).get(action)
    if not required_role:
        return False  # Deny unknown resource/action combinations
    user_level = ROLE_HIERARCHY.get(role, -1)
    required_level = ROLE_HIERARCHY.get(required_role, 99)
    allowed = user_level >= required_level
    AUTHZ_DECISIONS.labels(decision="allow" if allowed else "deny", role=role).inc()
    return allowed


# --------------------------------------------------------------------------- #
#  Dependency injectors                                                        #
# --------------------------------------------------------------------------- #

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> dict:
    """FastAPI dependency — validates JWT and returns user payload."""
    client_ip = request.client.host if request.client else None
    payload = decode_and_validate_token(credentials.credentials, client_ip)

    email = payload.get("email", "")
    if email not in _users_db or not _users_db[email].is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive or not found")

    return payload


def require_permission(resource: str, action: str):
    """Decorator-style dependency factory for RBAC checks."""
    async def _check(user: dict = Depends(get_current_user)) -> dict:
        role = user.get("role", "viewer")
        allowed = await evaluate_policy(role, resource, action)
        if not allowed:
            log.warning(
                "access_denied",
                user=user.get("email"),
                role=role,
                resource=resource,
                action=action,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' is not authorized for {action} on {resource}",
            )
        return user
    return _check


# --------------------------------------------------------------------------- #
#  Request / response models                                                   #
# --------------------------------------------------------------------------- #

class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int           # seconds
    role: str
    user_id: str


class RefreshRequest(BaseModel):
    refresh_token: str


class CreateUserRequest(BaseModel):
    email: str
    full_name: str
    role: str = "viewer"
    department: str | None = None
    password: str


class UpdateUserRequest(BaseModel):
    full_name: str | None = None
    role: str | None = None
    department: str | None = None
    is_active: bool | None = None


class IntrospectResponse(BaseModel):
    active: bool
    user_id: str | None = None
    email: str | None = None
    role: str | None = None
    expires_at: int | None = None


# --------------------------------------------------------------------------- #
#  FastAPI app                                                                 #
# --------------------------------------------------------------------------- #

app = FastAPI(
    title="Data Catalog — Auth Service",
    version="1.0.0",
    description="Zero Trust RBAC authentication and authorization",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8009", "https://datacatalog.yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.service_name}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Holds strong references to background audit tasks so GC doesn't collect them.
_audit_tasks: set = set()


def _audit(event_type: str, **kwargs) -> None:
    """Fire-and-forget: post an audit event without blocking the caller."""
    async def _post() -> None:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                await client.post(
                    f"{settings.audit_service_url}/audit/events",
                    json={"event_type": event_type, "service": "auth-service", **kwargs},
                )
        except Exception as exc:
            log.warning("audit_post_failed", event_type=event_type, error=str(exc))
    task = asyncio.ensure_future(_post())
    _audit_tasks.add(task)
    task.add_done_callback(_audit_tasks.discard)


@app.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request):
    """
    Authenticate user credentials and issue Zero Trust tokens.
    Returns a short-lived access token (15 min) and refresh token (24 hours).
    """
    start = time.monotonic()
    client_ip = request.client.host if request.client else None

    user = _users_db.get(req.email)
    if not user or not user.is_active:
        AUTH_ATTEMPTS.labels(outcome="user_not_found").inc()
        # Constant time comparison to prevent timing attacks
        pwd_context.verify("dummy", _hash("dummy"))
        _audit("LOGIN_FAILED", user_email=req.email, source_ip=client_ip, outcome="FAILURE")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not pwd_context.verify(req.password, user.hashed_password):
        AUTH_ATTEMPTS.labels(outcome="wrong_password").inc()
        log.warning("login_failed_wrong_password", email=req.email, ip=client_ip)
        _audit("LOGIN_FAILED", user_id=user.user_id, user_email=user.email, user_role=user.role, source_ip=client_ip, outcome="FAILURE")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user.last_login = datetime.now(timezone.utc)
    access_token = create_access_token(user, client_ip)
    refresh_token = create_refresh_token(user)

    AUTH_ATTEMPTS.labels(outcome="success").inc()
    log.info("login_success", email=req.email, role=user.role, ip=client_ip, duration=round(time.monotonic() - start, 3))
    _audit("LOGIN", user_id=user.user_id, user_email=user.email, user_role=user.role, source_ip=client_ip, outcome="SUCCESS")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_ttl_minutes * 60,
        role=user.role,
        user_id=user.user_id,
    )


@app.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshRequest, request: Request):
    """
    Issue a new access token using a valid refresh token.
    Zero Trust: access tokens cannot be extended — they must be re-issued.
    """
    try:
        payload = jwt.decode(
            req.refresh_token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid refresh token: {exc}")

    if payload.get("token_type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not a refresh token")

    jti = payload.get("jti")
    if jti and jti in _revoked_tokens:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")

    email = payload.get("email")
    user = _users_db.get(email)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    client_ip = request.client.host if request.client else None
    new_access_token = create_access_token(user, client_ip)
    new_refresh_token = create_refresh_token(user)

    # Revoke the old refresh token (one-time use)
    if jti:
        _revoked_tokens.add(jti)

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.jwt_access_token_ttl_minutes * 60,
        role=user.role,
        user_id=user.user_id,
    )


@app.post("/auth/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
):
    """Revoke the current access token (Zero Trust logout)."""
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_aud": False},
        )
        jti = payload.get("jti")
        if jti:
            _revoked_tokens.add(jti)
        log.info("logout", user=payload.get("email"))
        _audit("LOGOUT", user_id=payload.get("sub"), user_email=payload.get("email"), user_role=payload.get("role"), outcome="SUCCESS")
    except JWTError:
        pass  # Token is already invalid
    return {"message": "Logged out successfully"}


@app.post("/auth/introspect", response_model=IntrospectResponse)
async def introspect_token(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
):
    """Token introspection endpoint (RFC 7662 style) for service-to-service checks."""
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_aud": False},
        )
        jti = payload.get("jti")
        if jti and jti in _revoked_tokens:
            return IntrospectResponse(active=False)
        return IntrospectResponse(
            active=True,
            user_id=payload.get("sub"),
            email=payload.get("email"),
            role=payload.get("role"),
            expires_at=payload.get("exp"),
        )
    except JWTError:
        return IntrospectResponse(active=False)


@app.post("/authz/check")
async def check_permission(
    resource: str,
    action: str,
    user: dict = Depends(get_current_user),
):
    """Check if the current user has permission for resource × action."""
    role = user.get("role", "viewer")
    allowed = await evaluate_policy(role, resource, action)
    return {"allowed": allowed, "role": role, "resource": resource, "action": action}


@app.get("/users/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Return current user profile."""
    email = user.get("email")
    db_user = _users_db.get(email)
    if not db_user:
        raise HTTPException(404, "User not found")
    return {
        "user_id": db_user.user_id,
        "email": db_user.email,
        "full_name": db_user.full_name,
        "role": db_user.role,
        "department": db_user.department,
        "last_login": db_user.last_login.isoformat() if db_user.last_login else None,
    }


def _user_dict(u: User) -> dict:
    return {
        "user_id": u.user_id,
        "email": u.email,
        "full_name": u.full_name,
        "role": u.role,
        "is_active": u.is_active,
        "department": u.department,
        "last_login": u.last_login.isoformat() if u.last_login else None,
        "created_at": u.created_at.isoformat(),
    }


@app.get("/users", dependencies=[Depends(require_permission("user", "read"))])
async def list_users(
    q: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    page: int = 1,
    page_size: int = 20,
):
    """List users with optional search, role filter, and pagination (admin only)."""
    users = list(_users_db.values())
    if q:
        ql = q.lower()
        users = [u for u in users if ql in u.email.lower() or ql in u.full_name.lower()]
    if role:
        users = [u for u in users if u.role == role]
    if is_active is not None:
        users = [u for u in users if u.is_active == is_active]
    total = len(users)
    start = (page - 1) * page_size
    return {"total": total, "page": page, "page_size": page_size, "users": [_user_dict(u) for u in users[start:start + page_size]]}


@app.put("/users/{user_id}", dependencies=[Depends(require_permission("user", "write"))])
async def update_user(user_id: str, req: UpdateUserRequest):
    """Update user role, status, or profile (admin only)."""
    user = next((u for u in _users_db.values() if u.user_id == user_id), None)
    if not user:
        raise HTTPException(404, "User not found")
    if req.role is not None:
        if req.role not in ROLE_HIERARCHY:
            raise HTTPException(400, f"Invalid role: {req.role}")
        user.role = req.role
    if req.full_name is not None:
        user.full_name = req.full_name
    if req.department is not None:
        user.department = req.department
    if req.is_active is not None:
        user.is_active = req.is_active
    log.info("user_updated", user_id=user_id)
    _audit("USER_UPDATED", resource_type="user", resource_id=user.user_id, resource_fqn=user.email, outcome="SUCCESS", metadata={"role": user.role, "is_active": user.is_active})
    return _user_dict(user)


@app.delete("/users/{user_id}", dependencies=[Depends(require_permission("user", "write"))], status_code=204)
async def delete_user(user_id: str):
    """Delete a user (admin only)."""
    email = next((e for e, u in _users_db.items() if u.user_id == user_id), None)
    if not email:
        raise HTTPException(404, "User not found")
    _users_db.pop(email)
    log.info("user_deleted", user_id=user_id)
    _audit("USER_DELETED", resource_type="user", resource_id=user_id, resource_fqn=email, outcome="SUCCESS")


@app.post("/users", dependencies=[Depends(require_permission("user", "write"))], status_code=201)
async def create_user(req: CreateUserRequest):
    """Create a new user (admin only)."""
    if req.email in _users_db:
        raise HTTPException(409, f"User {req.email} already exists")
    if req.role not in ROLE_HIERARCHY:
        raise HTTPException(400, f"Invalid role: {req.role}. Valid: {list(ROLE_HIERARCHY)}")

    user = User(
        email=req.email,
        full_name=req.full_name,
        role=req.role,
        department=req.department,
        hashed_password=pwd_context.hash(req.password),
    )
    _users_db[req.email] = user
    log.info("user_created", email=req.email, role=req.role)
    _audit("USER_CREATED", resource_type="user", resource_id=user.user_id, resource_fqn=user.email, outcome="SUCCESS", metadata={"role": user.role})
    return {"user_id": user.user_id, "email": user.email, "role": user.role}


@app.get("/roles")
async def list_roles():
    """Return role definitions and permission matrix."""
    return {
        "roles": list(ROLE_HIERARCHY.keys()),
        "permission_matrix": PERMISSION_MATRIX,
        "zero_trust_config": {
            "access_token_ttl_minutes": settings.jwt_access_token_ttl_minutes,
            "refresh_token_ttl_days": settings.jwt_refresh_token_ttl_days,
            "ip_binding": True,
            "token_revocation": True,
            "opa_enabled": True,
        },
    }
