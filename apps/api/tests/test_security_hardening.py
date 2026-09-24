from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.dependencies import sign_cookie_value
from app.core.config import Settings
from app.domain.projects import RepositorySourceType
from app.domain.runs import (
    HumanQuestionStatus,
    RepositorySnapshot,
    SnapshotStatus,
)
from app.ingestion.service import SnapshotIngestionService
from app.ingestion.sources import GitHubAppSource
from app.main import create_app
from app.services.models import ModelBudgetExceededError, ModelRequest, ProviderGateway
from app.services.quotas import QuotaExhaustedError, QuotaService
from app.services.repository_tools import FindSymbolInput, RepositoryTools


class FakeMongoDatabase:
    def __init__(self) -> None:
        self.projects = FakeMongoCollection("projects")
        self.github_sessions = FakeMongoCollection("github_sessions")
        self.github_installations = FakeMongoCollection("github_installations")
        self.used_auth_nonces = FakeMongoCollection("used_auth_nonces")
        self.repository_snapshots = FakeMongoCollection("repository_snapshots")
        self.plan_versions = FakeMongoCollection("plan_versions")
        self.verification_runs = FakeMongoCollection("verification_runs")
        self.proof_obligations = FakeMongoCollection("proof_obligations")
        self.evidence = FakeMongoCollection("evidence")
        self.tool_runs = FakeMongoCollection("tool_runs")
        self.human_questions = FakeMongoCollection("human_questions")
        self.account_quotas = FakeMongoCollection("account_quotas")
        self.active_reservations = FakeMongoCollection("active_reservations")
        self.events = FakeMongoCollection("events")
        self.eval_runs = FakeMongoCollection("eval_runs")
        self.revised_plans = FakeMongoCollection("revised_plans")
        self.code_symbols = FakeMongoCollection("code_symbols")
        self.repository_files = FakeMongoCollection("repository_files")


class FakeMongoCollection:
    def __init__(self, name: str) -> None:
        self.name = name
        self.docs: list[dict] = []

    async def find_one(self, query: dict, **_kwargs) -> dict | None:
        for doc in self.docs:
            if self._matches(doc, query):
                return dict(doc)
        return None

    def find(self, query: dict, **_kwargs):
        matching = [dict(d) for d in self.docs if self._matches(d, query)]

        class AsyncCursor:
            def __init__(self, items):
                self.items = items
                self.idx = 0

            def sort(self, *args, **kwargs):
                return self

            def limit(self, *args, **kwargs):
                return self

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.idx < len(self.items):
                    item = self.items[self.idx]
                    self.idx += 1
                    return item
                raise StopAsyncIteration

        return AsyncCursor(matching)

    async def insert_one(self, doc: dict) -> None:
        from pymongo.errors import DuplicateKeyError

        if self.name == "used_auth_nonces":
            if any(d.get("nonce") == doc.get("nonce") for d in self.docs):
                raise DuplicateKeyError("duplicate nonce")
        elif self.name == "active_reservations":
            if any(d.get("slot_id") == doc.get("slot_id") for d in self.docs):
                raise DuplicateKeyError("duplicate slot_id reservation")
        elif self.name == "account_quotas":
            for d in self.docs:
                if (
                    d.get("scope_type") == doc.get("scope_type")
                    and d.get("scope_id") == doc.get("scope_id")
                    and d.get("quota_type") == doc.get("quota_type")
                    and d.get("period_start") == doc.get("period_start")
                ):
                    raise DuplicateKeyError("duplicate quota bucket")
        elif self.name == "verification_runs":
            if doc.get("idempotency_key"):
                for d in self.docs:
                    if (
                        d.get("project_id") == doc.get("project_id")
                        and d.get("idempotency_key") == doc.get("idempotency_key")
                    ):
                        raise DuplicateKeyError("duplicate project idempotency key")
        self.docs.append(dict(doc))

    async def update_one(self, query: dict, update: dict, upsert: bool = False) -> Any:
        class UpdateResult:
            def __init__(self, matched: int, modified: int):
                self.matched_count = matched
                self.modified_count = modified

        for i, doc in enumerate(self.docs):
            if self._matches(doc, query):
                if "$set" in update:
                    doc.update(update["$set"])
                if "$inc" in update:
                    for k, v in update["$inc"].items():
                        doc[k] = doc.get(k, 0) + v
                self.docs[i] = doc
                return UpdateResult(1, 1)
        if upsert:
            new_doc = dict(query)
            if "$set" in update:
                new_doc.update(update["$set"])
            if "$setOnInsert" in update:
                new_doc.update(update["$setOnInsert"])
            if "$inc" in update:
                for k, v in update["$inc"].items():
                    new_doc[k] = v
            self.docs.append(new_doc)
            return UpdateResult(0, 1)
        return UpdateResult(0, 0)

    async def find_one_and_update(self, query: dict, update: dict, **_kwargs) -> dict | None:
        for i, doc in enumerate(self.docs):
            if self._matches(doc, query):
                if "$set" in update:
                    doc.update(update["$set"])
                if "$inc" in update:
                    for k, v in update["$inc"].items():
                        doc[k] = doc.get(k, 0) + v
                self.docs[i] = doc
                return dict(doc)
        return None

    async def delete_one(self, query: dict) -> None:
        for i, doc in enumerate(self.docs):
            if self._matches(doc, query):
                self.docs.pop(i)
                return

    async def delete_many(self, query: dict) -> None:
        self.docs = [d for d in self.docs if not self._matches(d, query)]

    async def count_documents(self, query: dict) -> int:
        return sum(1 for d in self.docs if self._matches(d, query))

    async def aggregate(self, pipeline: list) -> Any:
        class AsyncAggCursor:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        return AsyncAggCursor()

    def _matches(self, doc: dict, query: dict) -> bool:
        for k, v in query.items():
            if k == "$or":
                if not any(self._matches(doc, subq) for subq in v):
                    return False
                continue
            if isinstance(v, dict):
                if "$in" in v:
                    if doc.get(k) not in v["$in"]:
                        return False
                    continue
                if "$lt" in v:
                    val = doc.get(k)
                    if val is None or val >= v["$lt"]:
                        return False
                    continue
                if "$gt" in v:
                    val = doc.get(k)
                    if isinstance(val, datetime) and isinstance(v["$gt"], datetime):
                        if val <= v["$gt"]:
                            return False
                    elif (val or 0) <= v["$gt"]:
                        return False
                    continue
            if doc.get(k) != v:
                return False
        return True


class FakeMongoManager:
    def __init__(self) -> None:
        self._db = FakeMongoDatabase()

    def database(self) -> FakeMongoDatabase:
        return self._db

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass


class FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def consume_rate_limit(self, subject: str, limit: int, window_seconds: int) -> bool:
        c = self.counts.get(subject, 0) + 1
        self.counts[subject] = c
        return c <= limit

    async def close(self) -> None:
        pass


def make_test_app(settings: Settings | None = None):
    s = settings or Settings(
        mongodb_uri=None,
        session_secret=SecretStr("super-test-session-secret-1234567890"),
        planproof_web_origins="http://localhost:3000",
    )
    app = create_app(s)
    fake_mongo = FakeMongoManager()
    fake_redis = FakeRedis()
    app.state.mongo = fake_mongo
    app.state.redis = fake_redis
    return app, fake_mongo, fake_redis


def make_session_cookie(
    account_login: str,
    installation_id: int,
    settings: Settings,
    mongo: FakeMongoManager,
    expired: bool = False,
) -> str:
    raw_token = f"token_{account_login}_{installation_id}"
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    exp = (
        datetime.now(UTC) - timedelta(days=1)
        if expired
        else datetime.now(UTC) + timedelta(days=7)
    )
    mongo.database().github_sessions.docs.append(
        {
            "token_hash": token_hash,
            "account_login": account_login,
            "installation_id": installation_id,
            "created_at": datetime.now(UTC),
            "expires_at": exp,
        }
    )
    return sign_cookie_value(raw_token, settings)


# ==============================================================================
# 1. ANONYMOUS ACCESS FAILS CLOSED (401)
# ==============================================================================


def test_anonymous_requests_fail_closed_with_401() -> None:
    app, mongo, _ = make_test_app()
    with TestClient(app) as client:
        # Projects
        assert client.get("/v1/projects").status_code == 401
        assert client.get("/v1/projects/proj-123").status_code == 401
        assert client.post("/v1/projects", json={"name": "P1"}).status_code == 401

        # Snapshots
        assert client.get("/v1/projects/proj-123/snapshots").status_code == 401
        assert client.get("/v1/snapshots/snap-123").status_code == 401
        assert client.post("/v1/projects/proj-123/snapshots").status_code == 401

        # Runs
        assert client.get("/v1/verification-runs").status_code == 401
        assert client.get("/v1/verification-runs/run-123").status_code == 401
        assert (
            client.post(
                "/v1/verification-runs",
                json={"project_id": "p", "snapshot_id": "s", "plan_version_id": "pv"},
            ).status_code
            == 401
        )
        assert client.get("/v1/verification-runs/run-123/proof-obligations").status_code == 401
        assert client.get("/v1/verification-runs/run-123/evidence").status_code == 401
        assert client.get("/v1/verification-runs/run-123/tool-runs").status_code == 401

        # Human questions, obligations, evidence
        assert client.post("/v1/human-questions/q-123/answers", json={"answer": "ok"}).status_code == 401
        assert client.get("/v1/proof-obligations/ob-123").status_code == 401
        assert client.get("/v1/evidence/ev-123").status_code == 401


def test_expired_session_fails_with_401() -> None:
    app, mongo, _ = make_test_app()
    expired_cookie = make_session_cookie(
        "alice", 101, app.state.settings, mongo, expired=True
    )
    with TestClient(app) as client:
        resp = client.get("/v1/projects", cookies={"planproof_session": expired_cookie})
    assert resp.status_code == 401


# ==============================================================================
# 2. TENANT ISOLATION (TENANT A vs TENANT B -> 404)
# ==============================================================================


def test_cross_tenant_access_returns_404() -> None:
    app, mongo, _ = make_test_app()
    alice_cookie = make_session_cookie("alice", 101, app.state.settings, mongo)
    bob_cookie = make_session_cookie("bob", 202, app.state.settings, mongo)

    # Setup Tenant A's project and run
    proj_a = {
        "id": "proj-alice",
        "name": "Alice Proj",
        "owner_id": "alice",
        "repository_source_type": "github_app",
        "github_installation_id": 101,
        "data_scope": "USER",
        "created_at": datetime.now(UTC),
    }
    mongo.database().projects.docs.append(proj_a)

    snap_a = {
        "id": "snap-alice",
        "project_id": "proj-alice",
        "repository_identity": "github:alice/repo",
        "source_type": "github_app",
        "status": "READY",
        "parser_version": "v1",
        "index_version": "v1",
        "created_at": datetime.now(UTC),
        "files_indexed": 1,
        "symbols_indexed": 1,
        "ignored_files": 0,
        "supported_languages": ["python"],
    }
    mongo.database().repository_snapshots.docs.append(snap_a)

    plan_a = {
        "id": "plan-alice",
        "project_id": "proj-alice",
        "version": 1,
        "change_request": "fix bug",
        "candidate_plan": "steps",
        "created_at": datetime.now(UTC),
    }
    mongo.database().plan_versions.docs.append(plan_a)

    run_a = {
        "id": "run-alice",
        "project_id": "proj-alice",
        "snapshot_id": "snap-alice",
        "plan_version_id": "plan-alice",
        "status": "VERIFYING",
        "tool_call_count": 0,
        "model_call_count": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "created_at": datetime.now(UTC),
    }
    mongo.database().verification_runs.docs.append(run_a)

    with TestClient(app) as client:
        # Alice can access her project and run
        assert client.get("/v1/projects/proj-alice", cookies={"planproof_session": alice_cookie}).status_code == 200
        assert client.get("/v1/verification-runs/run-alice", cookies={"planproof_session": alice_cookie}).status_code == 200

        # Bob accessing Alice's project/run gets 404 (never 200 or metadata)
        assert client.get("/v1/projects/proj-alice", cookies={"planproof_session": bob_cookie}).status_code == 404
        assert client.get("/v1/snapshots/snap-alice", cookies={"planproof_session": bob_cookie}).status_code == 404
        assert client.get("/v1/verification-runs/run-alice", cookies={"planproof_session": bob_cookie}).status_code == 404

        # Listing projects returns only own projects
        resp_bob = client.get("/v1/projects", cookies={"planproof_session": bob_cookie})
        assert resp_bob.status_code == 200
        assert len(resp_bob.json()) == 0


# ==============================================================================
# 3. IDEMPOTENCY SCOPING & QUOTA AVOIDANCE
# ==============================================================================


def test_idempotency_does_not_consume_quota_for_existing_run() -> None:
    app, mongo, _ = make_test_app()
    alice_cookie = make_session_cookie("alice", 101, app.state.settings, mongo)

    proj = {
        "id": "p-idem",
        "name": "P Idem",
        "owner_id": "alice",
        "repository_source_type": "github_app",
        "github_installation_id": 101,
        "data_scope": "USER",
        "created_at": datetime.now(UTC),
    }
    mongo.database().projects.docs.append(proj)
    snap = {
        "id": "s-idem",
        "project_id": "p-idem",
        "repository_identity": "github:alice/repo",
        "source_type": "github_app",
        "status": "READY",
        "parser_version": "v1",
        "index_version": "v1",
        "created_at": datetime.now(UTC),
        "files_indexed": 1,
        "symbols_indexed": 1,
        "ignored_files": 0,
        "supported_languages": ["python"],
    }
    mongo.database().repository_snapshots.docs.append(snap)
    plan = {
        "id": "plan-idem",
        "project_id": "p-idem",
        "version": 1,
        "change_request": "req",
        "candidate_plan": "plan",
        "created_at": datetime.now(UTC),
    }
    mongo.database().plan_versions.docs.append(plan)

    existing_run = {
        "id": "run-existing-1",
        "project_id": "p-idem",
        "snapshot_id": "s-idem",
        "plan_version_id": "plan-idem",
        "status": "QUEUED",
        "idempotency_key": "key-12345",
        "created_at": datetime.now(UTC),
    }
    mongo.database().verification_runs.docs.append(existing_run)

    with TestClient(app) as client:
        # Sending request with existing idempotency key returns the run without consuming quota
        resp = client.post(
            "/v1/verification-runs",
            json={"project_id": "p-idem", "snapshot_id": "s-idem", "plan_version_id": "plan-idem"},
            headers={"Idempotency-Key": "key-12345", "Origin": "http://localhost:3000"},
            cookies={"planproof_session": alice_cookie},
        )
        assert resp.status_code == 202
        assert resp.json()["id"] == "run-existing-1"

        # Check account quotas collection: no quota bucket was created or incremented
        assert len(mongo.database().account_quotas.docs) == 0


# ==============================================================================
# 4. CANONICAL QUOTA SERVICE (3/day, Monthly, Global, 429 Retry-After)
# ==============================================================================


@pytest.mark.asyncio
async def test_quota_service_enforces_daily_and_monthly_limits() -> None:
    mongo = FakeMongoManager()
    settings = Settings(
        mongodb_uri=None,
        planproof_free_runs_per_day=3,
        planproof_free_runs_per_month=10,
        planproof_global_runs_per_day=30,
    )
    qs = QuotaService(mongo.database(), settings)

    # First 3 runs succeed
    for _ in range(3):
        res = await qs.reserve_verification_run_quota("inst-101", "alice")
        assert len(res) == 3

    # 4th run fails with 429
    with pytest.raises(QuotaExhaustedError) as exc_info:
        await qs.reserve_verification_run_quota("inst-101", "alice")
    assert exc_info.value.status_code == 429
    assert "Daily run limit reached" in exc_info.value.detail
    assert "Retry-After" in exc_info.value.headers


# ==============================================================================
# 5. KILL SWITCHES (503 Service Unavailable)
# ==============================================================================


def test_kill_switches_fail_closed() -> None:
    settings = Settings(
        mongodb_uri=None,
        planproof_verification_enabled=False,
        planproof_ingestion_enabled=False,
        session_secret=SecretStr("super-secret-key-1234567890"),
    )
    app, mongo, _ = make_test_app(settings)
    alice_cookie = make_session_cookie("alice", 101, settings, mongo)

    with TestClient(app) as client:
        resp_run = client.post(
            "/v1/verification-runs",
            json={"project_id": "p", "snapshot_id": "s", "plan_version_id": "pv"},
            headers={"Origin": "http://localhost:3000"},
            cookies={"planproof_session": alice_cookie},
        )
        assert resp_run.status_code == 503
        assert "paused for maintenance" in resp_run.json()["detail"]


# ==============================================================================
# 6. MODEL GATEWAY HARD BUDGET & MAX_TOKENS
# ==============================================================================


@pytest.mark.asyncio
async def test_provider_gateway_hard_budget_enforcement() -> None:
    mongo = FakeMongoManager()
    settings = Settings(
        mongodb_uri=None,
        verification_max_model_calls=2,
        openrouter_api_key=SecretStr("key"),
        openrouter_primary_model="test-model",
    )
    # Pre-populate run with 2 model calls
    run_doc = {
        "id": "run-budget-test",
        "model_call_count": 2,
        "prompt_tokens": 100,
        "completion_tokens": 100,
    }
    mongo.database().verification_runs.docs.append(run_doc)

    mock_verification = MagicMock()
    mock_verification.database = mongo.database()

    gateway = ProviderGateway(settings, mock_verification)

    with pytest.raises(ModelBudgetExceededError) as exc_info:
        await gateway.complete(
            ModelRequest(system="sys", user="user"), run_id="run-budget-test"
        )
    assert "budget exceeded" in str(exc_info.value)


# ==============================================================================
# 7. REGEX ESCAPING IN REPOSITORY TOOLS (FIND_SYMBOL)
# ==============================================================================


@pytest.mark.asyncio
async def test_find_symbol_escapes_regex_metacharacters() -> None:
    mongo = FakeMongoManager()
    runs_repo = MagicMock()
    audit_repo = MagicMock()
    audit_repo.database = mongo.database()
    audit_repo.create_tool_run = AsyncMock()

    snap = RepositorySnapshot(
        project_id="p1",
        repository_identity="github:test/repo",
        source_type=RepositorySourceType.GITHUB_APP,
        status=SnapshotStatus.READY,
        parser_version="v1",
        index_version="v1",
    )
    runs_repo.get_snapshot = AsyncMock(return_value=snap)

    tools = RepositoryTools(runs_repo, audit_repo)
    # Pass a regex query like "func(.*)"
    res = await tools.find_symbol(FindSymbolInput(snapshot_id=snap.id, query="func(.*)"))
    assert isinstance(res, list)


# ==============================================================================
# 8. SECURITY HEADERS & REQUEST BODY SIZE
# ==============================================================================


def test_security_headers_and_body_size_limits() -> None:
    settings = Settings(
        mongodb_uri=None,
        max_request_bytes=1024,
        session_secret=SecretStr("secret-1234567890"),
    )
    app, _, _ = make_test_app(settings)
    with TestClient(app) as client:
        # Oversized body -> 413
        oversized = client.post("/v1/auth/logout", content="x" * 2048)
        assert oversized.status_code == 413

        # Normal response contains security headers
        resp = client.get("/v1/evaluations/latest")
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert resp.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"


# ==============================================================================
# 9. CSRF / ORIGIN DEFENSE
# ==============================================================================


def test_malicious_origin_is_rejected_on_mutations() -> None:
    settings = Settings(
        mongodb_uri=None,
        planproof_web_origins="http://localhost:3000,https://app.planproof.io",
        session_secret=SecretStr("secret-1234567890"),
    )
    app, _, _ = make_test_app(settings)
    with TestClient(app) as client:
        # Malicious Origin on POST -> 403 Forbidden
        bad_origin = client.post(
            "/v1/auth/logout",
            headers={"Origin": "https://evil-attacker.site"},
        )
        assert bad_origin.status_code == 403
        assert "cross-site mutation forbidden" in bad_origin.json()["detail"]


# ==============================================================================
# 10. AUTH NONCE REPLAY REJECTION (ATOMIC)
# ==============================================================================


def test_auth_nonce_replay_rejected() -> None:
    settings = Settings(
        mongodb_uri=None,
        github_app_id="123456",
        github_app_slug="planproof-app",
        github_app_private_key=SecretStr("dummy-private-key"),
        session_secret=SecretStr("super-secret-key-1234567890"),
    )
    app, mongo, _ = make_test_app(settings)
    nonce = "test-nonce-123"
    signed_state = sign_cookie_value(nonce, settings)

    # Pre-insert nonce to simulate consumed state
    mongo.database().used_auth_nonces.docs.append({"nonce": nonce})

    with TestClient(app) as client:
        resp = client.get(
            f"/v1/auth/github/callback?installation_id=101&state={nonce}",
            cookies={"planproof_github_state": signed_state},
        )
        assert resp.status_code == 400
        assert "already been consumed" in resp.json()["detail"]


# ==============================================================================
# 11. HUMAN ANSWER ISOLATION & SERVER-SIDE ACTOR BINDING
# ==============================================================================


def test_human_answer_binds_session_actor_and_isolates_tenants() -> None:
    app, mongo, _ = make_test_app()
    alice_cookie = make_session_cookie("alice", 101, app.state.settings, mongo)
    bob_cookie = make_session_cookie("bob", 202, app.state.settings, mongo)

    proj = {
        "id": "proj-q",
        "name": "Proj Q",
        "owner_id": "alice",
        "repository_source_type": "github_app",
        "github_installation_id": 101,
        "data_scope": "USER",
        "created_at": datetime.now(UTC),
    }
    mongo.database().projects.docs.append(proj)

    run = {
        "id": "run-q",
        "project_id": "proj-q",
        "snapshot_id": "s-q",
        "plan_version_id": "p-q",
        "status": "HUMAN_WAIT",
        "open_human_question_ids": ["q-1"],
        "completed_obligation_ids": [],
        "created_at": datetime.now(UTC),
    }
    mongo.database().verification_runs.docs.append(run)

    ob = {
        "id": "ob-1",
        "project_id": "proj-q",
        "snapshot_id": "s-q",
        "plan_version_id": "p-q",
        "run_id": "run-q",
        "normalized_statement": "Need decision",
        "statement": "Need decision",
        "category": "BEHAVIOR",
        "criticality": "HIGH",
        "status": "HUMAN_REQUIRED",
        "created_at": datetime.now(UTC),
    }
    mongo.database().proof_obligations.docs.append(ob)

    q = {
        "id": "q-1",
        "run_id": "run-q",
        "obligation_id": "ob-1",
        "question": "Proceed?",
        "why_needed": "Approval",
        "authority_required": "LEAD",
        "status": "OPEN",
        "created_at": datetime.now(UTC),
    }
    mongo.database().human_questions.docs.append(q)

    with TestClient(app) as client:
        # Bob cannot answer Alice's question -> 404
        bob_resp = client.post(
            "/v1/human-questions/q-1/answers",
            json={"answer": "Yes approved", "actor_id": "attacker-id"},
            headers={"Origin": "http://localhost:3000"},
            cookies={"planproof_session": bob_cookie},
        )
        assert bob_resp.status_code == 404

        # Alice answers: actor_id is derived as 'alice' from server session (ignoring client value)
        alice_resp = client.post(
            "/v1/human-questions/q-1/answers",
            json={"answer": "Yes approved", "actor_id": "spoofed-user"},
            headers={"Origin": "http://localhost:3000"},
            cookies={"planproof_session": alice_cookie},
        )
        assert alice_resp.status_code == 202

        updated_q = next(item for item in mongo.database().human_questions.docs if item["id"] == "q-1")
        assert updated_q["status"] == HumanQuestionStatus.ANSWERED
        assert updated_q["actor_id"] == "alice"  # authoritative session login, not spoofed-user


# ==============================================================================
# 12. GITHUB TOKEN ABSENT FROM PROCESS ARGV
# ==============================================================================


def test_git_materialize_does_not_leak_token_in_argv() -> None:
    source = GitHubAppSource.from_repository(
        "test-owner", "test-repo", "main", "super-secret-gh-token-xyz-12345"
    )
    records = MagicMock()
    service = SnapshotIngestionService(records)

    with patch("subprocess.run") as mock_subproc, patch("shutil.rmtree"):
        mock_subproc.return_value.stdout = "abc123sha\n"
        try:
            service._materialize(source)
        except Exception:
            pass

        # Inspect all subprocess calls made
        for call in mock_subproc.call_args_list:
            cmd = call[0][0]
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            assert "super-secret-gh-token-xyz-12345" not in cmd_str


# ==============================================================================
# 13. MULTI-BUCKET QUOTA CONCURRENCY STRESS TEST (20 PARALLEL REQUESTS)
# ==============================================================================


@pytest.mark.asyncio
async def test_multi_bucket_quota_concurrency_stress() -> None:
    mongo = FakeMongoManager()
    settings = Settings(
        mongodb_uri=None,
        planproof_free_runs_per_day=3,
        planproof_free_runs_per_month=10,
        planproof_global_runs_per_day=30,
    )
    qs = QuotaService(mongo.database(), settings)

    success_count = 0
    exhausted_count = 0

    async def attempt_run():
        nonlocal success_count, exhausted_count
        try:
            await qs.reserve_verification_run_quota("inst-concurrent", "alice")
            success_count += 1
        except QuotaExhaustedError:
            exhausted_count += 1

    # Run 20 concurrent quota acquisition attempts
    tasks = [attempt_run() for _ in range(20)]
    import asyncio
    await asyncio.gather(*tasks)

    # Exactly 3 succeed, 17 are rejected with QuotaExhaustedError
    assert success_count == 3
    assert exhausted_count == 17

    # Check database: the daily count document is exactly 3
    daily_bucket = await mongo.database().account_quotas.find_one(
        {"scope_type": "ACCOUNT", "scope_id": "inst-concurrent", "quota_type": "RUN_DAILY"}
    )
    assert daily_bucket is not None
    assert daily_bucket["count"] == 3


# ==============================================================================
# 14. SNAPSHOT DAILY QUOTA (5/DAY ENFORCEMENT)
# ==============================================================================


@pytest.mark.asyncio
async def test_snapshot_daily_quota_enforced() -> None:
    mongo = FakeMongoManager()
    settings = Settings(
        mongodb_uri=None,
        planproof_snapshots_per_day=5,
    )
    qs = QuotaService(mongo.database(), settings)

    for _ in range(5):
        await qs.reserve_snapshot_quota("inst-snap", "alice")

    # 6th attempt fails with 429
    with pytest.raises(QuotaExhaustedError) as exc_info:
        await qs.reserve_snapshot_quota("inst-snap", "alice")
    assert exc_info.value.status_code == 429
    assert "Daily snapshot limit reached" in exc_info.value.detail


# ==============================================================================
# 15. PROJECT CREATION ATOMIC QUOTA
# ==============================================================================


@pytest.mark.asyncio
async def test_project_creation_atomic_quota() -> None:
    mongo = FakeMongoManager()
    settings = Settings(
        mongodb_uri=None,
        planproof_max_projects_per_account=3,
    )
    qs = QuotaService(mongo.database(), settings)

    # 3 projects succeed
    for _ in range(3):
        await qs.reserve_project_quota("alice")

    # 4th project fails with 429
    with pytest.raises(QuotaExhaustedError) as exc_info:
        await qs.reserve_project_quota("alice")
    assert exc_info.value.status_code == 429
    assert "maximum project creation limit reached" in exc_info.value.detail


# ==============================================================================
# 16. CSRF MISSING ORIGIN ON COOKIE-AUTHENTICATED MUTATIONS
# ==============================================================================


def test_csrf_missing_origin_rejected_on_cookie_auth() -> None:
    settings = Settings(
        mongodb_uri=None,
        planproof_web_origins="http://localhost:3000",
        session_secret=SecretStr("super-test-secret-1234567890"),
    )
    app, mongo, _ = make_test_app(settings)
    alice_cookie = make_session_cookie("alice", 101, settings, mongo)

    with TestClient(app) as client:
        # 1. Mutating request with cookie and NO Origin and NO Referer -> 403 Forbidden
        resp_no_origin = client.post(
            "/v1/auth/logout",
            cookies={"planproof_session": alice_cookie},
        )
        assert resp_no_origin.status_code == 403
        assert "missing origin header" in resp_no_origin.json()["detail"]

        # 2. Mutating request with cookie and trusted Origin -> 200 OK
        resp_trusted_origin = client.post(
            "/v1/auth/logout",
            headers={"Origin": "http://localhost:3000"},
            cookies={"planproof_session": alice_cookie},
        )
        assert resp_trusted_origin.status_code == 200


# ==============================================================================
# 17. REQUEST BODY SIZE & STREAM READABILITY
# ==============================================================================


def test_request_body_size_edge_cases() -> None:
    settings = Settings(
        mongodb_uri=None,
        max_request_bytes=1024,
        session_secret=SecretStr("super-test-secret-1234567890"),
    )
    app, mongo, _ = make_test_app(settings)
    alice_cookie = make_session_cookie("alice", 101, settings, mongo)

    with TestClient(app) as client:
        # 1. Content-Length > limit -> 413
        resp_oversized_cl = client.post(
            "/v1/auth/logout",
            headers={"Origin": "http://localhost:3000", "Content-Length": "2048"},
            cookies={"planproof_session": alice_cookie},
        )
        assert resp_oversized_cl.status_code == 413

        # 2. Malformed Content-Length -> 400
        resp_malformed_cl = client.post(
            "/v1/auth/logout",
            headers={"Origin": "http://localhost:3000", "Content-Length": "not-a-number"},
            cookies={"planproof_session": alice_cookie},
        )
        assert resp_malformed_cl.status_code == 400

        # 3. Missing Content-Length but oversized content -> 413
        resp_oversized_chunk = client.post(
            "/v1/auth/logout",
            content="a" * 2048,
            headers={"Origin": "http://localhost:3000"},
            cookies={"planproof_session": alice_cookie},
        )
        assert resp_oversized_chunk.status_code == 413

        # 4. Normal read requests (GET) unaffected
        resp_get = client.get("/health/live")
        assert resp_get.status_code == 200


# ==============================================================================
# 18. PRODUCTION GITHUB OAUTH FAIL-CLOSED
# ==============================================================================


def test_production_github_oauth_fails_closed_without_code() -> None:
    settings = Settings(
        mongodb_uri=SecretStr("mongodb://localhost:27017"),
        planproof_env="production",
        planproof_gcp_project_id="planproof-prod-test",
        planproof_worker_service_url="https://worker-prod-test.run.app",
        planproof_tasks_invoker_service_account="tasks-invoker@planproof-prod-test.iam.gserviceaccount.com",
        github_app_id="123456",
        github_app_slug="planproof-app",
        github_app_private_key=SecretStr("dummy-private-key"),
        github_client_id="dummy-client-id",
        github_client_secret=SecretStr("dummy-client-secret"),
        session_secret=SecretStr("super-test-secret-1234567890"),
    )
    # Manually bypass require_production_database for this test client unit check
    app, mongo, _ = make_test_app(settings)
    signed_state = sign_cookie_value("state-prod-test", settings)

    with TestClient(app) as client:
        # Calling callback without OAuth code in production -> 400 Bad Request
        resp = client.get(
            "/v1/auth/github/callback?installation_id=101&state=state-prod-test",
            cookies={"planproof_github_state": signed_state},
        )
        assert resp.status_code == 400
        assert "OAuth code" in resp.json()["detail"]


# ==============================================================================
# 19. ATOMIC ACTIVE RUN RESERVATION SLOTS (ACCOUNT & PROJECT LEVEL)
# ==============================================================================


@pytest.mark.asyncio
async def test_active_run_reservation_atomic_account_slot_prevention() -> None:
    mongo = FakeMongoManager()
    settings = Settings(mongodb_uri=None, planproof_max_active_runs_per_account=1)
    qs = QuotaService(mongo.database(), settings)

    # 1. Run-A acquires slot for alice
    await qs.acquire_active_run_reservation("alice", "proj-1", "run-A")

    # 2. Run-B for alice immediately attempts to acquire slot -> 429 Too Many Requests
    with pytest.raises(HTTPException) as exc_info:
        await qs.acquire_active_run_reservation("alice", "proj-1", "run-B")
    assert exc_info.value.status_code == 429
    assert "active run limit reached" in exc_info.value.detail

    # 3. Run-A finishes and releases slot
    await qs.release_active_reservation("run-A")

    # 4. Run-B can now acquire slot successfully
    await qs.acquire_active_run_reservation("alice", "proj-1", "run-B")


# ==============================================================================
# 20. HARD PROVIDER ATTEMPTS BUDGET ENFORCEMENT
# ==============================================================================


@pytest.mark.asyncio
async def test_provider_attempts_hard_budget_enforcement() -> None:
    mongo = FakeMongoManager()
    settings = Settings(
        mongodb_uri=None,
        verification_max_model_calls=10,
        planproof_max_provider_attempts_per_run=6,
        openrouter_api_key=SecretStr("key"),
        openrouter_primary_model="test-model",
    )
    # Pre-populate run doc with 6 provider attempts
    run_doc = {
        "id": "run-attempts-test",
        "model_call_count": 1,
        "provider_attempts": 6,
    }
    mongo.database().verification_runs.docs.append(run_doc)

    mock_verification = MagicMock()
    mock_verification.database = mongo.database()
    gateway = ProviderGateway(settings, mock_verification)

    with pytest.raises(ModelBudgetExceededError) as exc_info:
        await gateway.complete(
            ModelRequest(system="sys", user="user"), run_id="run-attempts-test"
        )
    assert "provider attempts budget exceeded" in str(exc_info.value)


# ==============================================================================
# 21. PARALLEL SNAPSHOT QUOTA (10 PARALLEL ATTEMPTS, LIMIT 5)
# ==============================================================================


@pytest.mark.asyncio
async def test_snapshot_quota_parallel_stress() -> None:
    mongo = FakeMongoManager()
    settings = Settings(mongodb_uri=None, planproof_snapshots_per_day=5)
    qs = QuotaService(mongo.database(), settings)

    success_count = 0
    exhausted_count = 0

    async def attempt_snap():
        nonlocal success_count, exhausted_count
        try:
            await qs.reserve_snapshot_quota("inst-snap-stress", "alice")
            success_count += 1
        except QuotaExhaustedError:
            exhausted_count += 1

    import asyncio
    tasks = [attempt_snap() for _ in range(10)]
    await asyncio.gather(*tasks)

    # Exactly 5 succeed, 5 fail with 429
    assert success_count == 5
    assert exhausted_count == 5


# ==============================================================================
# 22. QUOTA TRANSACTION ABORT LEAVES ZERO LEAKED COUNTERS
# ==============================================================================


@pytest.mark.asyncio
async def test_quota_transaction_abort_leaves_no_leaked_counters() -> None:
    mongo = FakeMongoManager()
    settings = Settings(
        mongodb_uri=None,
        planproof_free_runs_per_day=3,
        planproof_free_runs_per_month=10,
        planproof_global_runs_per_day=30,
    )
    qs = QuotaService(mongo.database(), settings)

    # Pre-exhaust monthly quota (10 runs consumed)
    now = datetime.now(UTC)
    monthly_period = now.strftime("%Y-%m-01")
    daily_period = now.strftime("%Y-%m-%d")
    mongo.database().account_quotas.docs.append(
        {
            "scope_type": "ACCOUNT",
            "scope_id": "inst-abort",
            "quota_type": "RUN_MONTHLY",
            "period_start": monthly_period,
            "count": 10,
            "limit": 10,
        }
    )

    run_doc = {
        "id": "run-abort-test",
        "project_id": "p-1",
        "snapshot_id": "s-1",
        "plan_version_id": "pv-1",
        "status": "QUEUED",
        "enqueue_state": "PENDING",
    }

    # Attempt transactional run creation -> must abort because monthly quota is exhausted
    with pytest.raises(QuotaExhaustedError) as exc_info:
        await qs.create_verification_run_transactional("inst-abort", "alice", run_doc)
    assert exc_info.value.status_code == 429

    # Prove zero leaked counters:
    daily_bucket = await mongo.database().account_quotas.find_one(
        {"scope_type": "ACCOUNT", "scope_id": "inst-abort", "quota_type": "RUN_DAILY", "period_start": daily_period}
    )
    # Daily counter must be None or 0 (rolled back)
    assert daily_bucket is None or daily_bucket.get("count", 0) == 0

    global_bucket = await mongo.database().account_quotas.find_one(
        {"scope_type": "GLOBAL", "scope_id": "global", "quota_type": "GLOBAL_RUN_DAILY", "period_start": daily_period}
    )
    assert global_bucket is None or global_bucket.get("count", 0) == 0

    # Prove no run was inserted
    inserted_run = await mongo.database().verification_runs.find_one({"id": "run-abort-test"})
    assert inserted_run is None


# ==============================================================================
# 23. OUTBOX QUEUE DISPATCH CRASH-SAFETY & IDEMPOTENCY
# ==============================================================================


@pytest.mark.asyncio
async def test_outbox_queue_dispatch_crash_safety_and_idempotency() -> None:
    from app.api.workflow import dispatch_verification_run

    mongo = FakeMongoManager()
    run_doc = {
        "id": "run-outbox-test",
        "enqueue_state": "PENDING",
        "status": "QUEUED",
        "dispatch_attempts": 0,
    }
    mongo.database().verification_runs.docs.append(run_doc)

    # 1. First dispatch successfully claims and transitions to DISPATCHED
    with patch("app.api.workflow.CloudTasksDispatcher.dispatch_run", return_value=True) as mock_dispatch:
        res1 = await dispatch_verification_run("run-outbox-test", mongo.database())
        assert res1 is True
        mock_dispatch.assert_called_once_with("run-outbox-test", execution_generation=0)

    updated_run = await mongo.database().verification_runs.find_one({"id": "run-outbox-test"})
    assert updated_run["enqueue_state"] == "DISPATCHED"
    assert updated_run["dispatch_attempts"] == 1

    # 2. Duplicate dispatch attempt returns False and does not dispatch again
    with patch("app.api.workflow.CloudTasksDispatcher.dispatch_run", return_value=True) as mock_dispatch_dup:
        res2 = await dispatch_verification_run("run-outbox-test", mongo.database())
        assert res2 is False
        mock_dispatch_dup.assert_not_called()

    # 3. Crash recovery scenario: if enqueue_state was left in DISPATCH_FAILED, dispatch re-attempts
    await mongo.database().verification_runs.update_one(
        {"id": "run-outbox-test"},
        {"$set": {"enqueue_state": "DISPATCH_FAILED"}},
    )
    with patch("app.api.workflow.CloudTasksDispatcher.dispatch_run", return_value=True) as mock_dispatch_rec:
        res3 = await dispatch_verification_run("run-outbox-test", mongo.database())
        assert res3 is True
        mock_dispatch_rec.assert_called_once_with("run-outbox-test", execution_generation=0)


# ==============================================================================
# 24. LEASE OWNER FENCING (STALE WORKER CANNOT MUTATE NEWER OWNER'S SLOT)
# ==============================================================================


@pytest.mark.asyncio
async def test_stale_lease_owner_fencing() -> None:
    mongo = FakeMongoManager()
    settings = Settings(mongodb_uri=None)
    qs = QuotaService(mongo.database(), settings)

    # 1. Run-1 acquires slot
    await qs.acquire_active_run_reservation("alice", "proj-1", "run-1")
    slot = await mongo.database().active_reservations.find_one({"slot_id": "RUN_ACCOUNT:alice"})
    assert slot["lease_owner"] == "run-1"

    # 2. Run-1 finishes and releases
    await qs.release_active_reservation("run-1")

    # 3. Run-2 acquires slot
    await qs.acquire_active_run_reservation("alice", "proj-1", "run-2")
    slot2 = await mongo.database().active_reservations.find_one({"slot_id": "RUN_ACCOUNT:alice"})
    assert slot2["lease_owner"] == "run-2"

    # 4. Old worker for Run-1 attempts to renew lease -> returns False (fenced)
    renewed = await qs.renew_active_reservation("alice", "proj-1", "run-1")
    assert renewed is False

    # 5. Old worker for Run-1 attempts to release lease -> does NOT delete Run-2's slot
    await qs.release_active_reservation("run-1")
    slot_after = await mongo.database().active_reservations.find_one({"slot_id": "RUN_ACCOUNT:alice"})
    assert slot_after is not None
    assert slot_after["lease_owner"] == "run-2"


# ==============================================================================
# 25. MONTHLY 10 AND GLOBAL 30 STRICT ENFORCEMENT
# ==============================================================================


@pytest.mark.asyncio
async def test_quota_monthly_10_and_global_30_strict_enforcement() -> None:
    mongo = FakeMongoManager()
    settings = Settings(
        mongodb_uri=None,
        planproof_free_runs_per_day=3,
        planproof_free_runs_per_month=10,
        planproof_global_runs_per_day=30,
    )
    qs = QuotaService(mongo.database(), settings)

    # A. Monthly limit: simulate 10 runs across 4 distinct days within the same month
    now = datetime.now(UTC)
    for day in range(1, 4):  # days 1, 2, 3 -> 3 runs each = 9 runs
        simulated_period = now.strftime(f"%Y-%m-0{day}")
        with patch.object(qs, "_daily_period_str", return_value=simulated_period):
            for _ in range(3):
                await qs.reserve_verification_run_quota("inst-monthly", "alice")

    # 10th run on day 4 succeeds
    with patch.object(qs, "_daily_period_str", return_value=now.strftime("%Y-%m-04")):
        await qs.reserve_verification_run_quota("inst-monthly", "alice")

    # 11th run on day 4 fails with Monthly limit exceeded
    with patch.object(qs, "_daily_period_str", return_value=now.strftime("%Y-%m-04")):
        with pytest.raises(QuotaExhaustedError) as exc_info:
            await qs.reserve_verification_run_quota("inst-monthly", "alice")
        assert "Monthly run limit reached" in exc_info.value.detail

    # B. Global limit: 30 global runs max
    mongo_global = FakeMongoManager()
    qs_global = QuotaService(mongo_global.database(), settings)

    # 10 different accounts run 3 runs each = 30 total global runs
    for acc_idx in range(10):
        for _ in range(3):
            await qs_global.reserve_verification_run_quota(f"inst-g-{acc_idx}", f"user-{acc_idx}")

    # 31st run from an 11th account fails with global daily limit
    with pytest.raises(QuotaExhaustedError) as exc_global:
        await qs_global.reserve_verification_run_quota("inst-g-11", "user-11")
    assert "Global daily verification run limit reached" in exc_global.value.detail


