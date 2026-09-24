from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Cookie, Depends, HTTPException, Request, status

from app.core.config import Settings, get_settings
from app.db.mongo import MongoManager
from app.services.quotas import QuotaService

_SESSION_COOKIE = "__session"


def get_mongo(request: Request) -> MongoManager:
    return request.app.state.mongo


def get_settings_dep(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


def get_quota_service(
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> QuotaService:
    return QuotaService(mongo.database(), settings)


def sign_cookie_value(value: str, settings: Settings) -> str:
    if not settings.session_secret:
        return value
    secret = settings.session_secret.get_secret_value().encode()
    signature = hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()
    return f"{value}.{signature}"


def validate_signed_cookie(value: str | None, settings: Settings) -> str | None:
    if not value or "." not in value or not settings.session_secret:
        return None
    nonce, supplied = value.rsplit(".", 1)
    expected = sign_cookie_value(nonce, settings).rsplit(".", 1)[1]
    return nonce if hmac.compare_digest(supplied, expected) else None


def _extract_session_token(request: Request, cookie_param: str | None, settings: Settings) -> str | None:
    # 1. Check cookies (__session takes priority for Firebase Hosting, then planproof_session, then parameter)
    raw = request.cookies.get("__session") or request.cookies.get("planproof_session") or cookie_param
    if raw:
        validated = validate_signed_cookie(raw, settings)
        if validated:
            return validated

    # 2. Check Authorization: Bearer <signed_token> header
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        bearer_raw = auth[7:].strip()
        validated = validate_signed_cookie(bearer_raw, settings)
        if validated:
            return validated

    return None


async def get_optional_session(
    request: Request,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    planproof_session: Annotated[str | None, Cookie()] = None,
) -> dict[str, Any] | None:
    token = _extract_session_token(request, planproof_session, settings)
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    return await mongo.database().github_sessions.find_one(
        {
            "token_hash": token_hash,
            "expires_at": {"$gt": datetime.now(UTC)},
        }
    )


async def require_session(
    request: Request,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    planproof_session: Annotated[str | None, Cookie()] = None,
) -> dict[str, Any]:
    """Fail-closed authentication dependency. Supports __session cookie and Bearer auth."""
    token = _extract_session_token(request, planproof_session, settings)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    item = await mongo.database().github_sessions.find_one(
        {
            "token_hash": token_hash,
            "expires_at": {"$gt": datetime.now(UTC)},
        }
    )
    if not item:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired or invalid")
    return item


def verify_tenant_project_access(project: dict | Any, session: dict[str, Any]) -> None:
    """Enforce strict tenant isolation. Mismatch returns 404 (never leaking tenant presence)."""
    if not session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
    proj_dict = project.model_dump() if hasattr(project, "model_dump") else project
    proj_inst_id = proj_dict.get("github_installation_id")
    session_inst_id = session.get("installation_id")
    session_login = session.get("account_login")

    if proj_inst_id is not None:
        if proj_inst_id != session_inst_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "resource not found")
        return

    owner_id = proj_dict.get("owner_id")
    if owner_id and owner_id != session_login:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "resource not found")
    if not owner_id and not proj_inst_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "resource not found")


async def get_authorized_project(
    project_id: str,
    mongo: MongoManager,
    session: dict[str, Any],
) -> dict[str, Any]:
    project = await mongo.database().projects.find_one({"id": project_id})
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    verify_tenant_project_access(project, session)
    return project
