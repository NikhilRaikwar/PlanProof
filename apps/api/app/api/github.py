"""GitHub App installation, session, and selected-repository APIs.

Browser input is never accepted as repository authority.  The callback verifies
the installation with GitHub using an App JWT, and every repository/ref request
is constrained to that verified installation.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

import httpx
import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from app.api.dependencies import (
    get_mongo,
    get_quota_service,
    get_settings_dep,
    require_session,
    sign_cookie_value,
    validate_signed_cookie,
)
from app.core.config import Settings
from app.db.mongo import MongoManager
from app.domain.projects import Project, RepositorySourceType
from app.domain.runs import RepositorySnapshot
from app.ingestion.service import INDEX_VERSION, PARSER_VERSION, SnapshotIngestionService
from app.ingestion.sources import GitHubAppSource, seeded_fixture_source
from app.repositories.projects import ProjectsRepository
from app.repositories.runs import RunRepository
from app.services.quotas import QuotaService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["github"])
_STATE_COOKIE = "planproof_github_state"
_SESSION_COOKIE = "__session"
_GITHUB_API = "https://api.github.com"


def _resolve_fixtures_root() -> Path:
    env_root = os.environ.get("PLANPROOF_FIXTURES_ROOT")
    if env_root and Path(env_root).exists():
        return Path(env_root)
    curr = Path(__file__).resolve()
    for parent in curr.parents:
        candidate = parent / "demo-repos"
        if candidate.exists() and candidate.is_dir():
            return candidate
    return Path("/demo-repos")


_FIXTURES_ROOT = _resolve_fixtures_root()


class GitHubRepository(BaseModel):
    id: int
    owner: str
    name: str
    full_name: str
    private: bool
    default_branch: str


class GitHubRef(BaseModel):
    name: str
    commit_sha: str


class CreateConnectedSnapshotRequest(BaseModel):
    requested_ref: str | None = Field(default=None, max_length=128)


class GitHubAppClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _app_jwt(self) -> str:
        if not self.settings.github_app_is_configured:
            raise RuntimeError("GitHub App is not configured")
        pem = self.settings.github_private_key_pem
        if not pem:
            raise RuntimeError("GitHub App private key is not configured")
        now = datetime.now(UTC)
        return jwt.encode(
            {
                "iat": int((now - timedelta(seconds=30)).timestamp()),
                "exp": int((now + timedelta(minutes=9)).timestamp()),
                "iss": self.settings.github_app_id,
            },
            pem,
            algorithm="RS256",
        )

    async def _request(self, method: str, path: str, token: str, **kwargs: Any) -> dict:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.request(
                method, f"{_GITHUB_API}{path}", headers=headers, **kwargs
            )
        if response.status_code >= 400:
            raise RuntimeError(f"GitHub API request failed ({response.status_code})")
        return response.json()

    async def verify_installation(self, installation_id: int) -> dict:
        return await self._request("GET", f"/app/installations/{installation_id}", self._app_jwt())

    async def installation_token(self, installation_id: int) -> str:
        result = await self._request(
            "POST", f"/app/installations/{installation_id}/access_tokens", self._app_jwt()
        )
        token = result.get("token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("GitHub did not issue an installation token")
        return token

    async def repositories(self, installation_id: int) -> list[GitHubRepository]:
        payload = await self._request(
            "GET",
            "/installation/repositories?per_page=100",
            await self.installation_token(installation_id),
        )
        result: list[GitHubRepository] = []
        for item in payload.get("repositories", []):
            owner = item.get("owner", {}).get("login")
            if isinstance(owner, str) and isinstance(item.get("id"), int):
                result.append(
                    GitHubRepository(
                        id=item["id"],
                        owner=owner,
                        name=item["name"],
                        full_name=item["full_name"],
                        private=bool(item.get("private")),
                        default_branch=item.get("default_branch") or "main",
                    )
                )
        return result

    async def refs(self, installation_id: int, repository: GitHubRepository) -> list[GitHubRef]:
        token = await self.installation_token(installation_id)
        payload = await self._request(
            "GET",
            f"/repos/{quote(repository.owner)}/{quote(repository.name)}/branches?per_page=100",
            token,
        )
        return [
            GitHubRef(name=item["name"], commit_sha=item["commit"]["sha"])
            for item in payload
            if isinstance(item.get("name"), str)
            and isinstance(item.get("commit", {}).get("sha"), str)
        ]


def _client(settings: Settings) -> GitHubAppClient:
    return GitHubAppClient(settings)


async def _installation(session: dict, mongo: MongoManager) -> dict:
    record = await mongo.database().github_installations.find_one(
        {"installation_id": session["installation_id"]}
    )
    if not record:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "GitHub installation is unavailable")
    return record


@router.get("/auth/github/connect")
async def connect_github(
    settings: Annotated[Settings, Depends(get_settings_dep)],
):
    if not settings.github_app_is_configured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "GitHub connection is not configured"
        )
    nonce = secrets.token_urlsafe(32)
    url = (
        f"https://github.com/apps/{settings.github_app_slug}/installations/new?state={quote(nonce)}"
    )
    response = RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    response.set_cookie(
        _STATE_COOKIE,
        sign_cookie_value(nonce, settings),
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="none" if settings.session_cookie_secure else "lax",
        max_age=600,
        path="/",
    )
    return response


@router.get("/auth/github/callback")
async def github_callback(
    installation_id: int,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    state: str | None = None,
    code: str | None = None,
    setup_action: str | None = None,
    planproof_github_state: Annotated[str | None, Cookie()] = None,
):
    if state and planproof_github_state:
        expected = validate_signed_cookie(planproof_github_state, settings)
        if not expected or not hmac.compare_digest(expected, state):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid GitHub connection state")

        # Atomic single-insert guarded by unique index on nonce
        try:
            await mongo.database().used_auth_nonces.insert_one(
                {
                    "nonce": state,
                    "created_at": datetime.now(UTC),
                    "expires_at": datetime.now(UTC) + timedelta(minutes=15),
                }
            )
        except DuplicateKeyError:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "GitHub connection state has already been consumed"
            ) from None
    elif setup_action not in {"install", "update"} and not (code or state or installation_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "GitHub connection state is required")

    if settings.github_client_id and settings.github_client_secret and not code:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "GitHub user OAuth code is required"
        )

    client = _client(settings)
    try:
        installation = await client.verify_installation(installation_id)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "GitHub installation verification failed"
        ) from exc

    account = installation.get("account", {})
    inst_login = account.get("login")
    if not isinstance(inst_login, str):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "GitHub installation account is invalid")

    final_login = inst_login

    if code and settings.github_client_id and settings.github_client_secret:
        try:
            async with httpx.AsyncClient(timeout=10) as http_c:
                token_resp = await http_c.post(
                    "https://github.com/login/oauth/access_token",
                    headers={"Accept": "application/json"},
                    data={
                        "client_id": settings.github_client_id,
                        "client_secret": settings.github_client_secret.get_secret_value(),
                        "code": code,
                        "state": state or "",
                    },
                )
                if token_resp.status_code == 200:
                    user_token_data = token_resp.json()
                    u_token = user_token_data.get("access_token")
                    if u_token:
                        u_resp = await http_c.get(
                            f"{_GITHUB_API}/user",
                            headers={
                                "Authorization": f"Bearer {u_token}",
                                "Accept": "application/vnd.github+json",
                            },
                        )
                        if u_resp.status_code == 200:
                            user_data = u_resp.json()
                            user_login = user_data.get("login")
                            if user_login:
                                final_login = user_login
        except Exception as exc:
            logger.warning("github_user_oauth_failed error=%s", exc)

    existing_inst = await mongo.database().github_installations.find_one(
        {"installation_id": installation_id}
    )
    if existing_inst:
        existing_login = existing_inst.get("account_login")
        if existing_login and existing_login != final_login and existing_login != inst_login:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "installation is bound to another GitHub account"
            )

    now = datetime.now(UTC)
    await mongo.database().github_installations.update_one(
        {"installation_id": installation_id},
        {
            "$set": {
                "installation_id": installation_id,
                "account_login": final_login,
                "account_id": account.get("id"),
                "updated_at": now,
                "permissions": installation.get("permissions", {}),
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    await mongo.database().github_sessions.insert_one(
        {
            "token_hash": token_hash,
            "installation_id": installation_id,
            "account_login": final_login,
            "created_at": now,
            "expires_at": now + timedelta(days=7),
        }
    )
    signed_token = sign_cookie_value(token, settings)
    cookie_samesite = "none" if settings.session_cookie_secure else "lax"
    response = RedirectResponse(
        f"{settings.web_origins[0]}/workspace?session_token={quote(signed_token)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    response.set_cookie(
        _SESSION_COOKIE,
        signed_token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=cookie_samesite,
        max_age=7 * 24 * 60 * 60,
        path="/",
    )
    response.delete_cookie(_STATE_COOKIE, path="/")
    return response


class SessionClaimRequest(BaseModel):
    session_token: str


@router.post("/auth/session/claim")
async def claim_session(
    payload: SessionClaimRequest,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
):
    token = validate_signed_cookie(payload.session_token, settings)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid session token")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    session = await mongo.database().github_sessions.find_one(
        {
            "token_hash": token_hash,
            "expires_at": {"$gt": datetime.now(UTC)},
        }
    )
    if not session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired or not found")

    from fastapi.responses import JSONResponse

    cookie_samesite = "none" if settings.session_cookie_secure else "lax"
    resp = JSONResponse(
        {
            "connected": True,
            "account_login": session["account_login"],
            "installation_id": session["installation_id"],
            "session_token": payload.session_token,
        }
    )
    resp.set_cookie(
        _SESSION_COOKIE,
        payload.session_token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=cookie_samesite,
        max_age=7 * 24 * 60 * 60,
        path="/",
    )
    return resp


@router.get("/auth/session")
async def session_status(
    session: Annotated[dict, Depends(require_session)],
):
    return {
        "connected": True,
        "account_login": session["account_login"],
        "installation_id": session["installation_id"],
    }


@router.post("/auth/logout")
async def logout(
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    planproof_session: Annotated[str | None, Cookie()] = None,
):
    token = validate_signed_cookie(planproof_session, settings)
    if token:
        await mongo.database().github_sessions.delete_many(
            {"token_hash": hashlib.sha256(token.encode()).hexdigest()}
        )
    from fastapi.responses import JSONResponse

    response = JSONResponse({"connected": False})
    response.delete_cookie(_SESSION_COOKIE, path="/")
    return response


@router.get("/github/repositories", response_model=list[GitHubRepository])
async def connected_repositories(
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    session: Annotated[dict, Depends(require_session)],
):
    installation = await _installation(session, mongo)
    try:
        return await _client(settings).repositories(installation["installation_id"])
    except RuntimeError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "GitHub repositories are unavailable"
        ) from exc


@router.get("/workspace/projects", response_model=list[Project])
async def workspace_projects(
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    session: Annotated[dict, Depends(require_session)],
    include_demo: bool = False,
):
    query: dict[str, Any] = {"owner_id": session["account_login"]}
    if include_demo:
        query["data_scope"] = {"$in": ["USER", "DEMO"]}
    else:
        query["data_scope"] = "USER"
    cursor = mongo.database().projects.find(query).sort("created_at", -1)
    return [Project.model_validate(item) async for item in cursor]


@router.post(
    "/workspace/demo-snapshot",
    response_model=RepositorySnapshot,
    status_code=status.HTTP_201_CREATED,
)
async def create_demo_snapshot(
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    session: Annotated[dict, Depends(require_session)],
    quota_service: Annotated[QuotaService, Depends(get_quota_service)],
):
    account_key = str(session.get("installation_id") or session["account_login"])
    await quota_service.reserve_snapshot_quota(account_key, session["account_login"])

    project_document = await mongo.database().projects.find_one(
        {
            "owner_id": session["account_login"],
            "fixture_id": "partial-refunds-v1",
            "data_scope": "DEMO",
        }
    )
    project = (
        Project.model_validate(project_document)
        if project_document
        else Project(
            name="Partial Refund Demo",
            owner_id=session["account_login"],
            repository_source_type=RepositorySourceType.SEEDED,
            fixture_id="partial-refunds-v1",
            data_scope="DEMO",
        )
    )
    if not project_document:
        await ProjectsRepository(mongo).create(project)
    source = seeded_fixture_source("partial-refunds-v1", _FIXTURES_ROOT)
    records = RunRepository(mongo)
    snapshot = RepositorySnapshot(
        project_id=project.id,
        repository_identity=source.identity,
        source_type=source.source_type,
        requested_ref=source.requested_ref,
        parser_version=PARSER_VERSION,
        index_version=INDEX_VERSION,
    )
    await records.create_snapshot(snapshot)
    await quota_service.acquire_active_ingestion_reservation(session["account_login"], snapshot.id)
    try:
        result = await SnapshotIngestionService(records, settings=settings).ingest(snapshot.id, source)
        return result
    finally:
        await quota_service.release_active_reservation(snapshot.id)


@router.get("/github/repositories/{repository_id}/refs", response_model=list[GitHubRef])
async def repository_refs(
    repository_id: int,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    session: Annotated[dict, Depends(require_session)],
):
    installation = await _installation(session, mongo)
    client = _client(settings)
    repositories = await client.repositories(installation["installation_id"])
    repository = next((item for item in repositories if item.id == repository_id), None)
    if not repository:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "repository is not available through this installation"
        )
    return await client.refs(installation["installation_id"], repository)


@router.post(
    "/github/repositories/{repository_id}/snapshots",
    response_model=RepositorySnapshot,
    status_code=status.HTTP_201_CREATED,
)
async def create_connected_snapshot(
    repository_id: int,
    request: CreateConnectedSnapshotRequest,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    session: Annotated[dict, Depends(require_session)],
    quota_service: Annotated[QuotaService, Depends(get_quota_service)],
):
    account_key = str(session.get("installation_id") or session["account_login"])
    await quota_service.reserve_snapshot_quota(account_key, session["account_login"])

    installation = await _installation(session, mongo)
    client = _client(settings)
    repositories = await client.repositories(installation["installation_id"])
    repository = next((item for item in repositories if item.id == repository_id), None)
    if not repository:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "repository is not available through this installation"
        )
    refs = await client.refs(installation["installation_id"], repository)
    requested_ref = request.requested_ref or repository.default_branch
    if requested_ref not in {item.name for item in refs}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "requested ref is not available")
    projects = ProjectsRepository(mongo)
    existing = await mongo.database().projects.find_one(
        {
            "owner_id": session["account_login"],
            "github_repository_id": repository.id,
            "data_scope": "USER",
        }
    )
    project = (
        Project.model_validate(existing)
        if existing
        else Project(
            name=repository.full_name,
            owner_id=session["account_login"],
            repository_source_type=RepositorySourceType.GITHUB_APP,
            repository_url=f"https://github.com/{repository.full_name}",
            requested_ref=requested_ref,
            github_repository_id=repository.id,
            github_installation_id=installation["installation_id"],
            data_scope="USER",
        )
    )
    if not existing:
        await projects.create(project)
    token = await client.installation_token(installation["installation_id"])
    source = GitHubAppSource.from_repository(
        repository.owner, repository.name, requested_ref, token
    )
    records = RunRepository(mongo)
    snapshot = RepositorySnapshot(
        project_id=project.id,
        repository_identity=source.identity,
        source_type=source.source_type,
        requested_ref=requested_ref,
        parser_version=PARSER_VERSION,
        index_version=INDEX_VERSION,
    )
    await records.create_snapshot(snapshot)
    await quota_service.acquire_active_ingestion_reservation(session["account_login"], snapshot.id)
    try:
        result = await SnapshotIngestionService(records, settings=settings).ingest(snapshot.id, source)
        return result
    finally:
        await quota_service.release_active_reservation(snapshot.id)
