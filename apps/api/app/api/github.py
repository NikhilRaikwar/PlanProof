"""GitHub App installation, session, and selected-repository APIs.

Browser input is never accepted as repository authority.  The callback verifies
the installation with GitHub using an App JWT, and every repository/ref request
is constrained to that verified installation.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

import httpx
import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.api.dependencies import get_mongo, get_settings_dep
from app.core.config import Settings
from app.db.mongo import MongoManager
from app.domain.projects import Project, RepositorySourceType
from app.domain.runs import RepositorySnapshot
from app.ingestion.service import INDEX_VERSION, PARSER_VERSION, SnapshotIngestionService
from app.ingestion.sources import GitHubAppSource, seeded_fixture_source
from app.repositories.projects import ProjectsRepository
from app.repositories.runs import RunRepository

router = APIRouter(prefix="/v1", tags=["github"])
_STATE_COOKIE = "planproof_github_state"
_SESSION_COOKIE = "planproof_session"
_GITHUB_API = "https://api.github.com"
_FIXTURES_ROOT = Path(__file__).resolve().parents[4] / "demo-repos"


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


def _sign(value: str, settings: Settings) -> str:
    secret = settings.session_secret.get_secret_value().encode()
    signature = hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()
    return f"{value}.{signature}"


def _validate_signed(value: str | None, settings: Settings) -> str | None:
    if not value or "." not in value or not settings.session_secret:
        return None
    nonce, supplied = value.rsplit(".", 1)
    expected = _sign(nonce, settings).rsplit(".", 1)[1]
    return nonce if hmac.compare_digest(supplied, expected) else None


async def _session(mongo: MongoManager, settings: Settings, session_cookie: str | None) -> dict:
    token = _validate_signed(session_cookie, settings)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "GitHub connection required")
    item = await mongo.database().github_sessions.find_one(
        {
            "token_hash": hashlib.sha256(token.encode()).hexdigest(),
            "expires_at": {"$gt": datetime.now(UTC)},
        }
    )
    if not item:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "GitHub connection required")
    return item


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
        _sign(nonce, settings),
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=600,
        path="/v1/auth/github",
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
    if state is not None:
        expected = _validate_signed(planproof_github_state, settings)
        if not expected or not hmac.compare_digest(expected, state):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid GitHub connection state")
    try:
        installation = await _client(settings).verify_installation(installation_id)
    except RuntimeError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "GitHub installation verification failed"
        ) from exc
    account = installation.get("account", {})
    login = account.get("login")
    if not isinstance(login, str):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "GitHub installation account is invalid")
    now = datetime.now(UTC)
    await mongo.database().github_installations.update_one(
        {"installation_id": installation_id},
        {
            "$set": {
                "installation_id": installation_id,
                "account_login": login,
                "account_id": account.get("id"),
                "updated_at": now,
                "permissions": installation.get("permissions", {}),
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    token = secrets.token_urlsafe(32)
    await mongo.database().github_sessions.insert_one(
        {
            "token_hash": hashlib.sha256(token.encode()).hexdigest(),
            "installation_id": installation_id,
            "account_login": login,
            "created_at": now,
            "expires_at": now + timedelta(days=7),
        }
    )
    response = RedirectResponse(
        f"{settings.web_origins[0]}/workspace", status_code=status.HTTP_303_SEE_OTHER
    )
    response.set_cookie(
        _SESSION_COOKIE,
        _sign(token, settings),
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
        path="/",
    )
    response.delete_cookie(_STATE_COOKIE, path="/v1/auth/github")
    return response


@router.get("/auth/session")
async def session_status(
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    planproof_session: Annotated[str | None, Cookie()] = None,
):
    session = await _session(mongo, settings, planproof_session)
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
    token = _validate_signed(planproof_session, settings)
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
    planproof_session: Annotated[str | None, Cookie()] = None,
):
    session = await _session(mongo, settings, planproof_session)
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
    settings: Annotated[Settings, Depends(get_settings_dep)],
    planproof_session: Annotated[str | None, Cookie()] = None,
):
    session = await _session(mongo, settings, planproof_session)
    cursor = (
        mongo.database()
        .projects.find(
            {"owner_id": session["account_login"], "data_scope": {"$in": ["USER", "DEMO"]}}
        )
        .sort("created_at", -1)
    )
    return [Project.model_validate(item) async for item in cursor]


@router.post(
    "/workspace/demo-snapshot",
    response_model=RepositorySnapshot,
    status_code=status.HTTP_201_CREATED,
)
async def create_demo_snapshot(
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    planproof_session: Annotated[str | None, Cookie()] = None,
):
    session = await _session(mongo, settings, planproof_session)
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
    return await SnapshotIngestionService(records).ingest(snapshot.id, source)


@router.get("/github/repositories/{repository_id}/refs", response_model=list[GitHubRef])
async def repository_refs(
    repository_id: int,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    planproof_session: Annotated[str | None, Cookie()] = None,
):
    session = await _session(mongo, settings, planproof_session)
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
    planproof_session: Annotated[str | None, Cookie()] = None,
):
    session = await _session(mongo, settings, planproof_session)
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
    return await SnapshotIngestionService(records).ingest(snapshot.id, source)

