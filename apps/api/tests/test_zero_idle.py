from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from google.api_core.exceptions import AlreadyExists
from pydantic import SecretStr

from app.api.internal_tasks import verify_tasks_invoker_auth
from app.core.config import Settings
from app.main import create_app
from app.services.cloud_tasks import CloudTasksDispatcher
from app.services.quotas import QuotaService

# ---------------------------------------------------------------------------
# Test Helpers / Mocks
# ---------------------------------------------------------------------------


class MockCursor:
    def __init__(self, docs: list[dict]):
        self.docs = docs
        self._iter = iter(docs)

    def sort(self, *args, **kwargs):
        return self

    def limit(self, count: int):
        self.docs = self.docs[:count]
        self._iter = iter(self.docs)
        return self

    def __aiter__(self):
        self._iter = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration from None


class FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []

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
                elif "$lt" in v:
                    doc_val = doc.get(k)
                    if doc_val is None or doc_val >= v["$lt"]:
                        return False
                elif "$exists" in v:
                    if (k in doc) != v["$exists"]:
                        return False
            else:
                if doc.get(k) != v:
                    return False
        return True

    async def find_one(self, query: dict, *args, **kwargs) -> dict | None:
        for doc in self.docs:
            if self._matches(doc, query):
                return dict(doc)
        return None

    def find(self, query: dict, projection: dict | None = None):
        matched = [dict(d) for d in self.docs if self._matches(d, query)]
        return MockCursor(matched)

    async def insert_one(self, doc: dict):
        self.docs.append(dict(doc))
        return MagicMock(inserted_id="fake_id")

    async def update_one(self, query: dict, update: dict, upsert: bool = False):
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
            self.docs.append(new_doc)
            return UpdateResult(0, 1)
        return UpdateResult(0, 0)

    async def find_one_and_update(self, query: dict, update: dict, **_kwargs) -> dict | None:
        for i, doc in enumerate(self.docs):
            if self._matches(doc, query):
                old_doc = dict(doc)
                if "$set" in update:
                    doc.update(update["$set"])
                if "$inc" in update:
                    for k, v in update["$inc"].items():
                        doc[k] = doc.get(k, 0) + v
                self.docs[i] = doc
                return old_doc
        return None

    async def delete_one(self, query: dict) -> None:
        for i, doc in enumerate(self.docs):
            if self._matches(doc, query):
                self.docs.pop(i)
                return

    async def delete_many(self, query: dict) -> None:
        self.docs = [d for d in self.docs if not self._matches(d, query)]

    async def create_index(self, *args, **kwargs):
        pass

    async def create_indexes(self, *args, **kwargs):
        pass

    async def drop_index(self, *args, **kwargs):
        pass


class FakeDatabase:
    def __init__(self):
        self.account_quotas = FakeCollection()
        self.active_reservations = FakeCollection()
        self.projects = FakeCollection()
        self.repository_snapshots = FakeCollection()
        self.plan_versions = FakeCollection()
        self.verification_runs = FakeCollection()
        self.verification_results = FakeCollection()
        self.proof_obligations = FakeCollection()
        self.tool_runs = FakeCollection()
        self.evidence = FakeCollection()
        self.human_questions = FakeCollection()
        self.revised_plans = FakeCollection()
        self.github_installations = FakeCollection()
        self.users = FakeCollection()

    def get_collection(self, name: str):
        return getattr(self, name)

    def __getattr__(self, item: str):
        if item not in self.__dict__:
            self.__dict__[item] = FakeCollection()
        return self.__dict__[item]

    def __getitem__(self, item: str):
        if not hasattr(self, item):
            setattr(self, item, FakeCollection())
        return getattr(self, item)


class FakeMongoManager:
    def __init__(self):
        self._db = FakeDatabase()

    def database(self):
        return self._db

    async def ping(self):
        return True


def get_fake_prod_settings(role: str = "worker"):
    return Settings(
        mongodb_uri=SecretStr("mongodb://fake-atlas.mongodb.net:27017/planproof"),
        redis_url=None,
        planproof_env="production",
        planproof_runtime_role=role,
        planproof_gcp_project_id="planproof-prod-proj",
        planproof_cloud_tasks_location="asia-south1",
        planproof_cloud_tasks_queue="planproof-verification",
        planproof_worker_service_url="https://worker-prod-xyz.run.app",
        planproof_tasks_invoker_service_account="tasks-invoker@planproof-prod.iam.gserviceaccount.com",
        planproof_scheduler_invoker_service_account="scheduler-invoker@planproof-prod.iam.gserviceaccount.com",
        github_app_id="123456",
        github_app_slug="planproof-app",
        github_app_private_key=SecretStr("dummy-private-key"),
        github_client_id="dummy-client-id",
        github_client_secret=SecretStr("dummy-client-secret"),
        session_secret=SecretStr("super-test-secret-1234567890"),
    )


# ---------------------------------------------------------------------------
# Test 1 & 2: Production Boots Without REDIS_URL and Readiness Checks Pass
# ---------------------------------------------------------------------------


def test_production_boots_without_redis_url() -> None:
    settings = get_fake_prod_settings()
    assert settings.redis_url is None
    app = create_app(settings)
    assert app is not None


def test_readiness_does_not_require_redis() -> None:
    settings = get_fake_prod_settings()
    mongo = FakeMongoManager()
    app = create_app(settings)
    app.state.mongo = mongo

    with TestClient(app) as client:
        resp = client.get("/health/ready")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["status"] == "ok"
        assert data["mongo"] == "ok"
        assert data["queue"] == "cloud_tasks"
        assert "redis" not in data


# ---------------------------------------------------------------------------
# Test 3: Deterministic Task ID Generation & Human Resume Generation Bump
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execution_generation_and_task_naming_across_human_resume() -> None:
    settings = get_fake_prod_settings()
    dispatcher = CloudTasksDispatcher(settings)

    run_id = "00000000-0000-0000-0000-000000000001"

    # A. Initial execution (g0)
    task_name_g0 = dispatcher.build_task_name(run_id, execution_generation=0)
    assert (
        task_name_g0
        == f"projects/{settings.planproof_gcp_project_id}/locations/{settings.planproof_cloud_tasks_location}/queues/{settings.planproof_cloud_tasks_queue}/tasks/run-{run_id}-g0"
    )

    # B. Human resume execution (g1)
    task_name_g1 = dispatcher.build_task_name(run_id, execution_generation=1)
    assert (
        task_name_g1
        == f"projects/{settings.planproof_gcp_project_id}/locations/{settings.planproof_cloud_tasks_location}/queues/{settings.planproof_cloud_tasks_queue}/tasks/run-{run_id}-g1"
    )
    assert task_name_g0 != task_name_g1

    # C. Retrying g1 uses the same task name
    task_name_g1_retry = dispatcher.build_task_name(run_id, execution_generation=1)
    assert task_name_g1 == task_name_g1_retry

    # Verify dispatch payload includes execution_generation
    with patch.object(dispatcher, "_get_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client_factory.return_value = mock_client
        mock_client.queue_path.return_value = f"projects/{settings.planproof_gcp_project_id}/locations/{settings.planproof_cloud_tasks_location}/queues/{settings.planproof_cloud_tasks_queue}"
        mock_client.create_task.return_value = MagicMock(name=task_name_g1)

        success = await dispatcher.dispatch_run(run_id, execution_generation=1)
        assert success is True

        call_kwargs = mock_client.create_task.call_args[1]
        task_body = call_kwargs["request"]["task"]
        assert task_body["name"] == task_name_g1
        assert b'"execution_generation": 1' in task_body["http_request"]["body"]


# ---------------------------------------------------------------------------
# Test 4: Stale Generation Rejection by Worker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_generation_task_rejected_by_worker() -> None:
    settings = get_fake_prod_settings()
    mongo = FakeMongoManager()
    app = create_app(settings)
    app.state.mongo = mongo
    app.dependency_overrides[verify_tasks_invoker_auth] = lambda: {"email": settings.planproof_tasks_invoker_service_account}

    run_id = "run-stale-gen-test"
    # Canonical run is on generation 1
    await mongo.database().verification_runs.insert_one(
        {
            "id": run_id,
            "project_id": "proj-1",
            "execution_generation": 1,
            "status": "QUEUED",
        }
    )

    with patch("app.api.internal_tasks.VerificationWorkflow") as mock_wf_cls:
        mock_wf = MagicMock()
        mock_wf.run = AsyncMock()
        mock_wf_cls.return_value = mock_wf

        with TestClient(app) as client:
            # Stale g0 task arrives late
            resp = client.post(
                f"/internal/tasks/verification/{run_id}",
                headers={"Authorization": "Bearer fake-oidc-token"},
                json={"run_id": run_id, "execution_generation": 0},
            )
            assert resp.status_code == status.HTTP_200_OK
            assert resp.json()["status"] == "skipped_stale_generation"
            # Workflow must NOT execute
            mock_wf.run.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5: Outbox Crash Recovery (Stale DISPATCHING & Post-Create Crash)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_dispatching_outbox_recovery() -> None:
    settings = get_fake_prod_settings()
    mongo = FakeMongoManager()
    app = create_app(settings)
    app.state.mongo = mongo
    app.dependency_overrides[verify_tasks_invoker_auth] = lambda: {"email": settings.planproof_tasks_invoker_service_account}

    # Simulate a run stuck in DISPATCHING from an API crash > 60s ago
    stale_time = datetime.now(UTC) - timedelta(seconds=90)
    run_id = "run-crashed-dispatching-1"
    await mongo.database().verification_runs.insert_one(
        {
            "id": run_id,
            "status": "QUEUED",
            "enqueue_state": "DISPATCHING",
            "dispatch_claimed_at": stale_time,
            "execution_generation": 0,
            "dispatch_attempts": 1,
            "created_at": stale_time,
        }
    )

    with patch("app.services.cloud_tasks.CloudTasksDispatcher.dispatch_run", return_value=True) as mock_dispatch:
        with TestClient(app) as client:
            resp = client.post(
                "/internal/tasks/recover-dispatches?limit=20",
                headers={"Authorization": f"Bearer test-{settings.planproof_scheduler_invoker_service_account}-token"},
            )
            assert resp.status_code == status.HTTP_200_OK
            data = resp.json()
            assert data["scanned"] == 1
            assert data["dispatched"] == 1
            mock_dispatch.assert_called_once_with(run_id, execution_generation=0)

    recovered = await mongo.database().verification_runs.find_one({"id": run_id})
    assert recovered["enqueue_state"] == "DISPATCHED"
    assert recovered["dispatch_claimed_at"] is None


@pytest.mark.asyncio
async def test_crash_after_cloud_tasks_create_heals_via_already_exists() -> None:
    settings = get_fake_prod_settings()
    dispatcher = CloudTasksDispatcher(settings)
    run_id = "run-crash-heal-already-exists"

    with patch.object(dispatcher, "_get_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client_factory.return_value = mock_client
        mock_client.queue_path.return_value = "projects/p/locations/l/queues/q"
        # Cloud Tasks returns AlreadyExists because task was created before API process crashed
        mock_client.create_task.side_effect = AlreadyExists("Task already exists")

        success = await dispatcher.dispatch_run(run_id, execution_generation=0)
        assert success is True


# ---------------------------------------------------------------------------
# Test 6: Retry Before Lease Expiry Returns 503; Retry After Expiry Reclaims
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crash_and_retry_before_lease_expiry_receives_retryable_503() -> None:
    settings = get_fake_prod_settings()
    mongo = FakeMongoManager()
    app = create_app(settings)
    app.state.mongo = mongo

    run_id = "run-active-lease-retry-503"
    future_lease = datetime.now(UTC) + timedelta(seconds=90)
    await mongo.database().verification_runs.insert_one(
        {
            "id": run_id,
            "project_id": "proj-1",
            "execution_generation": 0,
            "status": "EXTRACTING_OBLIGATIONS",
            "execution_claim_id": "live-claim-uuid",
            "execution_lease_expires_at": future_lease,
        }
    )

    with patch("app.api.internal_tasks.VerificationWorkflow") as mock_wf_cls:
        mock_wf = MagicMock()
        mock_wf.run = AsyncMock()
        mock_wf_cls.return_value = mock_wf

        with TestClient(app) as client:
            resp = client.post(
                f"/internal/tasks/verification/{run_id}",
                headers={"Authorization": f"Bearer test-{settings.planproof_tasks_invoker_service_account}-token"},
                json={"run_id": run_id, "execution_generation": 0},
            )
            # Must NOT return HTTP 200; must return retryable HTTP 503 so Cloud Tasks retries!
            assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            assert resp.headers.get("Retry-After") == "15"
            mock_wf.run.assert_not_called()


@pytest.mark.asyncio
async def test_retry_after_lease_expiry_successfully_reclaims() -> None:
    settings = get_fake_prod_settings()
    mongo = FakeMongoManager()
    app = create_app(settings)
    app.state.mongo = mongo

    run_id = "run-expired-lease-reclaim"
    past_lease = datetime.now(UTC) - timedelta(seconds=10)
    await mongo.database().verification_runs.insert_one(
        {
            "id": run_id,
            "project_id": "proj-1",
            "execution_generation": 0,
            "status": "EXTRACTING_OBLIGATIONS",
            "execution_claim_id": "dead-claim-uuid",
            "execution_lease_expires_at": past_lease,
        }
    )

    with patch("app.api.internal_tasks.VerificationWorkflow") as mock_wf_cls:
        mock_wf = MagicMock()
        mock_wf.run = AsyncMock()
        mock_wf_cls.return_value = mock_wf

        with TestClient(app) as client:
            resp = client.post(
                f"/internal/tasks/verification/{run_id}",
                headers={"Authorization": f"Bearer test-{settings.planproof_tasks_invoker_service_account}-token"},
                json={"run_id": run_id, "execution_generation": 0},
            )
            assert resp.status_code == status.HTTP_200_OK
            assert resp.json()["status"] == "completed"
            mock_wf.run.assert_called_once_with(run_id)

    run_doc = await mongo.database().verification_runs.find_one({"id": run_id})
    assert run_doc["execution_claim_id"] != "dead-claim-uuid"


# ---------------------------------------------------------------------------
# Test 7: HUMAN_WAIT Behavior & Answer Persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_human_wait_cannot_execute_without_human_answer() -> None:
    settings = get_fake_prod_settings()
    mongo = FakeMongoManager()
    app = create_app(settings)
    app.state.mongo = mongo

    run_id = "run-human-wait-guard"
    await mongo.database().verification_runs.insert_one(
        {
            "id": run_id,
            "project_id": "proj-1",
            "execution_generation": 0,
            "status": "HUMAN_WAIT",
        }
    )

    with patch("app.api.internal_tasks.VerificationWorkflow") as mock_wf_cls:
        mock_wf = MagicMock()
        mock_wf.run = AsyncMock()
        mock_wf_cls.return_value = mock_wf

        with TestClient(app) as client:
            resp = client.post(
                f"/internal/tasks/verification/{run_id}",
                headers={"Authorization": f"Bearer test-{settings.planproof_tasks_invoker_service_account}-token"},
                json={"run_id": run_id, "execution_generation": 0},
            )
            # Returns HTTP 200 acknowledged without executing workflow
            assert resp.status_code == status.HTTP_200_OK
            assert resp.json()["status"] == "skipped_suspended_human_wait"
            mock_wf.run.assert_not_called()

    # Verify status remains suspended
    run_doc = await mongo.database().verification_runs.find_one({"id": run_id})
    assert run_doc["status"] == "HUMAN_WAIT"


@pytest.mark.asyncio
async def test_human_answer_persistence_and_generation_increment() -> None:
    from app.api.workflow import HumanAnswerRequest, answer_human_question
    from app.domain.runs import HumanQuestionStatus
    from app.domain.verification import ObligationStatus

    mongo = FakeMongoManager()
    settings = get_fake_prod_settings()
    qs = QuotaService(mongo.database(), settings)

    # 1. Seed project, run in HUMAN_WAIT, obligation, question
    project_doc = {"id": "proj-h", "owner_id": "nikhil", "data_scope": "USER"}
    await mongo.database().projects.insert_one(project_doc)

    run_doc = {
        "id": "run-h-1",
        "project_id": "proj-h",
        "snapshot_id": "snap-1",
        "plan_version_id": "plan-1",
        "status": "HUMAN_WAIT",
        "execution_generation": 0,
        "open_human_question_ids": ["q-1"],
        "completed_obligation_ids": [],
    }
    await mongo.database().verification_runs.insert_one(run_doc)

    q_doc = {
        "id": "q-1",
        "run_id": "run-h-1",
        "obligation_id": "ob-1",
        "question": "Is this authorized?",
        "why_needed": "Required for compliance",
        "authority_required": "REPO_ADMIN",
        "prompt": "Is this authorized?",
        "status": HumanQuestionStatus.OPEN.value,
        "created_at": datetime.now(UTC),
    }
    await mongo.database().human_questions.insert_one(q_doc)

    ob_doc = {
        "id": "ob-1",
        "run_id": "run-h-1",
        "project_id": "proj-h",
        "snapshot_id": "snap-1",
        "plan_version_id": "plan-1",
        "status": ObligationStatus.PENDING.value,
        "statement": "Check auth",
        "normalized_statement": "Check auth",
        "category": "BEHAVIOR",
        "criticality": "HIGH",
        "obligation_type": "STATEMENT",
        "created_at": datetime.now(UTC),
    }
    await mongo.database().proof_obligations.insert_one(ob_doc)

    session = {"account_login": "nikhil", "user_id": "u-nikhil", "data_scope": "USER"}
    req = HumanAnswerRequest(answer="Yes, proceed")

    with patch("app.api.workflow.dispatch_verification_run", return_value=True) as mock_dispatch:
        answered_q = await answer_human_question("q-1", req, mongo, settings, session, qs)
        assert answered_q.status == HumanQuestionStatus.ANSWERED
        assert answered_q.answer == "Yes, proceed"
        mock_dispatch.assert_called_once_with("run-h-1", mongo.database(), settings)

    # Verify run updated durably to generation 1 and status QUEUED
    updated_run = await mongo.database().verification_runs.find_one({"id": "run-h-1"})
    assert updated_run["status"] == "QUEUED"
    assert updated_run["enqueue_state"] == "PENDING"
    assert updated_run["execution_generation"] == 1


# ---------------------------------------------------------------------------
# Test 8: Heartbeat Renewal & Ownership Loss
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execution_heartbeat_renews_claim_lease() -> None:
    import asyncio

    from app.api.internal_tasks import _execution_claim_heartbeat

    mongo = FakeMongoManager()
    run_id = "run-hb-test"
    initial_expiry = datetime.now(UTC) + timedelta(seconds=10)
    await mongo.database().verification_runs.insert_one(
        {
            "id": run_id,
            "execution_generation": 0,
            "execution_claim_id": "claim-hb-1",
            "execution_lease_expires_at": initial_expiry,
        }
    )

    stop_ev = asyncio.Event()
    # Trigger one heartbeat tick with short interval
    hb_task = asyncio.create_task(
        _execution_claim_heartbeat(mongo.database(), run_id, 0, "claim-hb-1", stop_ev, interval_seconds=0)
    )
    await asyncio.sleep(0.05)
    stop_ev.set()
    await hb_task

    updated_run = await mongo.database().verification_runs.find_one({"id": run_id})
    assert updated_run["execution_lease_expires_at"] > initial_expiry


# ---------------------------------------------------------------------------
# Test 9: Parameterized Recoverable States Recovery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("crashed_status", ["EXTRACTING_OBLIGATIONS", "VERIFYING", "FINALIZING"])
async def test_recoverable_execution_states_parameterized(crashed_status: str) -> None:
    settings = get_fake_prod_settings()
    mongo = FakeMongoManager()
    app = create_app(settings)
    app.state.mongo = mongo

    run_id = f"run-recover-{crashed_status.lower()}"
    past_lease = datetime.now(UTC) - timedelta(seconds=30)
    await mongo.database().verification_runs.insert_one(
        {
            "id": run_id,
            "project_id": "proj-1",
            "execution_generation": 0,
            "status": crashed_status,
            "execution_claim_id": "dead-worker-claim",
            "execution_lease_expires_at": past_lease,
        }
    )

    with patch("app.api.internal_tasks.VerificationWorkflow") as mock_wf_cls:
        mock_wf = MagicMock()
        mock_wf.run = AsyncMock()
        mock_wf_cls.return_value = mock_wf

        with TestClient(app) as client:
            resp = client.post(
                f"/internal/tasks/verification/{run_id}",
                headers={"Authorization": f"Bearer test-{settings.planproof_tasks_invoker_service_account}-token"},
                json={"run_id": run_id, "execution_generation": 0},
            )
            assert resp.status_code == status.HTTP_200_OK
            assert resp.json()["status"] == "completed"
            mock_wf.run.assert_called_once_with(run_id)


# ---------------------------------------------------------------------------
# Test 10: Cross-Service-Account Invocation Is Rejected
# ---------------------------------------------------------------------------


def test_cross_service_account_caller_rejected() -> None:
    settings = get_fake_prod_settings()
    mongo = FakeMongoManager()
    app = create_app(settings)
    app.state.mongo = mongo

    with TestClient(app) as client:
        # Tasks Invoker SA attempting to call recovery endpoint -> rejected 403
        resp_rec = client.post(
            "/internal/tasks/recover-dispatches",
            headers={"Authorization": f"Bearer test-{settings.planproof_tasks_invoker_service_account}-token"},
        )
        assert resp_rec.status_code == status.HTTP_403_FORBIDDEN

        # Scheduler Invoker SA attempting to call verification endpoint -> rejected 403
        resp_ver = client.post(
            "/internal/tasks/verification/run-test-cross",
            headers={"Authorization": f"Bearer test-{settings.planproof_scheduler_invoker_service_account}-token"},
            json={"run_id": "run-test-cross", "execution_generation": 0},
        )
        assert resp_ver.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Test 11: Deployment Environment Variables Match Settings Exactly
# ---------------------------------------------------------------------------


def test_deployment_env_variables_instantiate_production_settings() -> None:
    env_dict = {
        "PLANPROOF_ENV": "production",
        "MONGODB_URI": "mongodb://prod-cluster.mongodb.net:27017/planproof",
        "MONGODB_DATABASE": "planproof",
        "PLANPROOF_GCP_PROJECT_ID": "planproof-ai",
        "PLANPROOF_CLOUD_TASKS_LOCATION": "asia-south1",
        "PLANPROOF_CLOUD_TASKS_QUEUE": "planproof-verification",
        "PLANPROOF_WORKER_SERVICE_URL": "https://planproof-verification-worker-lfrrer4z6q-el.a.run.app",
        "PLANPROOF_TASKS_INVOKER_SERVICE_ACCOUNT": "planproof-tasks-invoker@planproof-ai.iam.gserviceaccount.com",
        "PLANPROOF_SCHEDULER_INVOKER_SERVICE_ACCOUNT": "planproof-scheduler-invoker@planproof-ai.iam.gserviceaccount.com",
        "GITHUB_APP_ID": "12345",
        "GITHUB_APP_SLUG": "planproof",
        "GITHUB_APP_PRIVATE_KEY": "dummy-github-app-private-key",
        "GITHUB_CLIENT_ID": "gh-client-id",
        "GITHUB_CLIENT_SECRET": "gh-client-secret",
        "SESSION_SECRET": "01234567890123456789012345678901",
        "PLANPROOF_WEB_ORIGINS": "https://planproof.nikhilraikwar.me",
    }
    with patch.dict("os.environ", env_dict, clear=True):
        settings = Settings()
        assert settings.planproof_env == "production"
        assert settings.planproof_gcp_project_id == "planproof-ai"
        assert settings.planproof_cloud_tasks_location == "asia-south1"
        assert settings.planproof_cloud_tasks_queue == "planproof-verification"
        assert str(settings.planproof_worker_service_url) == "https://planproof-verification-worker-lfrrer4z6q-el.a.run.app/"
        assert settings.planproof_tasks_invoker_service_account == "planproof-tasks-invoker@planproof-ai.iam.gserviceaccount.com"
        assert settings.planproof_scheduler_invoker_service_account == "planproof-scheduler-invoker@planproof-ai.iam.gserviceaccount.com"


# ---------------------------------------------------------------------------
# Test 12: Cloud Tasks Dispatch Deadline Configuration (1800s)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cloud_tasks_dispatch_deadline_configured_to_1800s() -> None:
    settings = get_fake_prod_settings()
    dispatcher = CloudTasksDispatcher(settings)
    run_id = "run-deadline-1800-test"

    with patch.object(dispatcher, "_get_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client_factory.return_value = mock_client
        mock_client.queue_path.return_value = "projects/p/locations/l/queues/q"
        mock_client.create_task.return_value = MagicMock()

        success = await dispatcher.dispatch_run(run_id, execution_generation=0)
        assert success is True

        call_kwargs = mock_client.create_task.call_args[1]
        task_body = call_kwargs["request"]["task"]
        assert "dispatch_deadline" in task_body
        assert task_body["dispatch_deadline"].seconds == 1800


# ---------------------------------------------------------------------------
# Test 13: Runtime Role Route Separation (API vs Worker)
# ---------------------------------------------------------------------------


def test_runtime_role_route_separation() -> None:
    settings = get_fake_prod_settings()
    mongo = FakeMongoManager()

    # 1. API runtime role: mounts public API, does NOT mount internal task endpoints
    settings.planproof_runtime_role = "api"
    api_app = create_app(settings)
    api_app.state.mongo = mongo
    with TestClient(api_app) as client:
        # Internal task routes must be 404 (absent)
        resp_worker = client.post("/internal/tasks/verification/run-test-123")
        assert resp_worker.status_code == status.HTTP_404_NOT_FOUND

        resp_rec = client.post("/internal/tasks/recover-dispatches")
        assert resp_rec.status_code == status.HTTP_404_NOT_FOUND

    # 2. Worker runtime role: mounts internal task endpoints, does NOT mount public business routes
    settings.planproof_runtime_role = "worker"
    worker_app = create_app(settings)
    worker_app.state.mongo = mongo
    with TestClient(worker_app) as client:
        # Internal routes exist (returns 401 without auth header)
        resp_worker = client.post("/internal/tasks/verification/run-test-123")
        assert resp_worker.status_code == status.HTTP_401_UNAUTHORIZED

        # Public business routes are absent (404)
        resp_runs = client.post("/v1/workflow/verification-runs")
        assert resp_runs.status_code == status.HTTP_404_NOT_FOUND

    # 3. Invalid runtime role in production: fails closed
    settings.planproof_runtime_role = "invalid_role"
    with pytest.raises(ValueError, match="invalid PLANPROOF_RUNTIME_ROLE"):
        create_app(settings)


# ---------------------------------------------------------------------------
# Test 14: Worker OIDC Audience Validation
# ---------------------------------------------------------------------------


def test_worker_oidc_audience_validation() -> None:
    settings = get_fake_prod_settings()
    mongo = FakeMongoManager()
    settings.planproof_runtime_role = "worker"
    app = create_app(settings)
    app.state.mongo = mongo

    # Mock id_token.verify_oauth2_token
    with patch("app.api.internal_tasks.id_token.verify_oauth2_token") as mock_verify:
        mock_verify.return_value = {
            "email": settings.planproof_tasks_invoker_service_account,
            "aud": str(settings.planproof_worker_service_url).rstrip("/"),
        }

        with TestClient(app) as client:
            resp = client.post(
                "/internal/tasks/verification/run-aud-test",
                headers={"Authorization": "Bearer valid-real-jwt-token"},
                json={"run_id": "run-aud-test", "execution_generation": 0},
            )
            assert resp.status_code in (status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE)
            # Valid audience verified by id_token.verify_oauth2_token
            mock_verify.assert_called_once()
            called_audience = mock_verify.call_args[1]["audience"]
            assert called_audience == str(settings.planproof_worker_service_url).rstrip("/")

    # Mismatched audience raises exception in id_token.verify_oauth2_token
    with patch("app.api.internal_tasks.id_token.verify_oauth2_token") as mock_verify_fail:
        mock_verify_fail.side_effect = ValueError("Audience does not match")

        with TestClient(app) as client:
            resp_fail = client.post(
                "/internal/tasks/verification/run-aud-test",
                headers={"Authorization": "Bearer invalid-aud-jwt-token"},
                json={"run_id": "run-aud-test", "execution_generation": 0},
            )
            assert resp_fail.status_code == status.HTTP_401_UNAUTHORIZED
