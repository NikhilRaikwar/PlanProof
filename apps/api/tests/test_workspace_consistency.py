import hashlib
import hmac
import pytest
from datetime import UTC, datetime, timedelta
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.indexes import ensure_indexes
from app.db.mongo import MongoManager
from app.domain.common import new_id
from app.domain.projects import Project, RepositorySourceType
from app.domain.runs import (
    HumanQuestion,
    HumanQuestionStatus,
    PlanVersion,
    RepositorySnapshot,
    SnapshotStatus,
    VerificationRun,
    VerificationRunStatus,
)
from app.domain.verification import (
    Evidence,
    EvidenceType,
    ObligationCategory,
    ObligationStatus,
    ProofObligation,
    ToolRun,
    ToolRunStatus,
)
from app.main import create_app


def _sign(value: str, secret: str) -> str:
    sig = hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()
    return f"{value}.{sig}"


@pytest.mark.integration
async def test_workspace_projects_excludes_demo_by_default() -> None:
    settings = Settings()
    if not settings.mongo_is_configured:
        pytest.skip("MongoDB is required")
    mongo = MongoManager(settings)
    await mongo.connect()
    await ensure_indexes(mongo.database())
    db = mongo.database()

    account = f"test-user-{new_id()[:8]}"
    import random
    installation_id = random.randint(100_000, 999_999)
    now = datetime.now(UTC)

    # Insert installation & session
    await db.github_installations.insert_one(
        {
            "installation_id": installation_id,
            "account_login": account,
            "account_id": 1234,
            "updated_at": now,
            "created_at": now,
        }
    )
    token = new_id()
    await db.github_sessions.insert_one(
        {
            "token_hash": hashlib.sha256(token.encode()).hexdigest(),
            "installation_id": installation_id,
            "account_login": account,
            "created_at": now,
            "expires_at": now + timedelta(days=1),
        }
    )

    # Insert USER project and DEMO project
    user_proj = Project(
        name=f"{account}/real-repo",
        owner_id=account,
        repository_source_type=RepositorySourceType.GITHUB_APP,
        github_installation_id=installation_id,
        data_scope="USER",
    )
    demo_proj = Project(
        name="Partial Refund Demo",
        owner_id=account,
        repository_source_type=RepositorySourceType.SEEDED,
        fixture_id="partial-refunds-v1",
        data_scope="DEMO",
    )
    await db.projects.insert_one(user_proj.model_dump(mode="python"))
    await db.projects.insert_one(demo_proj.model_dump(mode="python"))

    cookie_val = _sign(token, settings.session_secret.get_secret_value())

    with TestClient(create_app(settings)) as client:
        client.cookies.set("planproof_session", cookie_val)

        # Default call: MUST ONLY return USER projects
        res = client.get("/v1/workspace/projects")
        assert res.status_code == 200
        names = [p["name"] for p in res.json()]
        assert user_proj.name in names
        assert "Partial Refund Demo" not in names

        # Explicit include_demo=true
        res_demo = client.get("/v1/workspace/projects?include_demo=true")
        assert res_demo.status_code == 200
        names_demo = [p["name"] for p in res_demo.json()]
        assert user_proj.name in names_demo
        assert "Partial Refund Demo" in names_demo

    await mongo.close()


@pytest.mark.integration
async def test_tenant_isolation_cross_installation() -> None:
    settings = Settings()
    if not settings.mongo_is_configured:
        pytest.skip("MongoDB is required")
    mongo = MongoManager(settings)
    await mongo.connect()
    await ensure_indexes(mongo.database())
    db = mongo.database()
    now = datetime.now(UTC)

    # Tenant 1: Installation 101
    user1 = f"user1-{new_id()[:6]}"
    inst1 = 10101
    token1 = new_id()
    await db.github_sessions.insert_one(
        {
            "token_hash": hashlib.sha256(token1.encode()).hexdigest(),
            "installation_id": inst1,
            "account_login": user1,
            "created_at": now,
            "expires_at": now + timedelta(days=1),
        }
    )
    proj1 = Project(
        name=f"{user1}/private-repo",
        owner_id=user1,
        repository_source_type=RepositorySourceType.GITHUB_APP,
        github_installation_id=inst1,
        data_scope="USER",
    )
    await db.projects.insert_one(proj1.model_dump(mode="python"))

    snap1 = RepositorySnapshot(
        project_id=proj1.id,
        repository_identity=f"github:{proj1.name}",
        requested_ref="main",
        resolved_commit_sha="111122223333",
        parser_version="v1",
        index_version="v1",
        status=SnapshotStatus.READY,
    )
    await db.repository_snapshots.insert_one(snap1.model_dump(mode="python"))

    plan1 = PlanVersion(
        project_id=proj1.id,
        version=1,
        change_request="Fix critical bug",
        candidate_plan="Steps...",
    )
    await db.plan_versions.insert_one(plan1.model_dump(mode="python"))

    run1 = VerificationRun(
        project_id=proj1.id,
        snapshot_id=snap1.id,
        plan_version_id=plan1.id,
        status=VerificationRunStatus.COMPLETE,
    )
    await db.verification_runs.insert_one(run1.model_dump(mode="python"))

    # Tenant 2: Installation 202
    user2 = f"user2-{new_id()[:6]}"
    inst2 = 20202
    token2 = new_id()
    await db.github_sessions.insert_one(
        {
            "token_hash": hashlib.sha256(token2.encode()).hexdigest(),
            "installation_id": inst2,
            "account_login": user2,
            "created_at": now,
            "expires_at": now + timedelta(days=1),
        }
    )

    with TestClient(create_app(settings)) as client:
        # User 2 tries to access User 1's run
        cookie2 = _sign(token2, settings.session_secret.get_secret_value())
        client.cookies.set("planproof_session", cookie2)

        # GET /verification-runs/{run1.id} MUST return 404
        res = client.get(f"/v1/verification-runs/{run1.id}")
        assert res.status_code == 404

        # GET /verification-runs/{run1.id}/evidence MUST return 404
        res_ev = client.get(f"/v1/verification-runs/{run1.id}/evidence")
        assert res_ev.status_code == 404

        # GET /verification-runs/{run1.id}/tool-runs MUST return 404
        res_tr = client.get(f"/v1/verification-runs/{run1.id}/tool-runs")
        assert res_tr.status_code == 404

        # GET /snapshots/{snap1.id} MUST return 404
        res_snap = client.get(f"/v1/snapshots/{snap1.id}", cookies={"planproof_session": cookie2})
        assert res_snap.status_code == 404

        # GET /projects/{proj1.id}/snapshots MUST return 404
        res_psnap = client.get(f"/v1/projects/{proj1.id}/snapshots", cookies={"planproof_session": cookie2})
        assert res_psnap.status_code == 404

        # GET /verification-runs?project_id={proj1.id} MUST return 404
        res_runs = client.get(f"/v1/verification-runs?project_id={proj1.id}")
        assert res_runs.status_code == 404

        # User 1 accesses their own run: MUST return 200 with DTOs
        cookie1 = _sign(token1, settings.session_secret.get_secret_value())
        client.cookies.set("planproof_session", cookie1)

        res_auth = client.get(f"/v1/verification-runs/{run1.id}")
        assert res_auth.status_code == 200
        data = res_auth.json()
        assert data["repository"]["id"] == proj1.id
        assert data["repository"]["name"] == proj1.name
        assert data["snapshot"]["resolved_commit_sha"] == "111122223333"
        assert data["plan"]["change_request"] == "Fix critical bug"

        # User 1 accesses their own snapshots: MUST return 200
        res_snap_auth = client.get(f"/v1/snapshots/{snap1.id}", cookies={"planproof_session": cookie1})
        assert res_snap_auth.status_code == 200
        assert res_snap_auth.json()["id"] == snap1.id

    await mongo.close()


@pytest.mark.integration
async def test_legacy_trace_attribution_when_no_exact_run_id() -> None:
    settings = Settings()
    if not settings.mongo_is_configured:
        pytest.skip("MongoDB is required")
    mongo = MongoManager(settings)
    await mongo.connect()
    await ensure_indexes(mongo.database())
    db = mongo.database()

    proj = Project(
        name="test-org/legacy-repo",
        owner_id="test-org",
        repository_source_type=RepositorySourceType.PUBLIC_GITHUB,
        data_scope="USER",
    )
    await db.projects.insert_one(proj.model_dump(mode="python"))

    snap = RepositorySnapshot(
        project_id=proj.id,
        repository_identity="github:test-org/legacy-repo",
        requested_ref="main",
        resolved_commit_sha="aabbcc112233",
        parser_version="v1",
        index_version="v1",
        status=SnapshotStatus.READY,
    )
    await db.repository_snapshots.insert_one(snap.model_dump(mode="python"))

    plan = PlanVersion(
        project_id=proj.id,
        version=1,
        change_request="Legacy verification",
        candidate_plan="Old plan text",
    )
    await db.plan_versions.insert_one(plan.model_dump(mode="python"))

    # Historical run with tool_call_count = 3, but NO run_id stamped on tool_runs and no linked evidence
    run = VerificationRun(
        project_id=proj.id,
        snapshot_id=snap.id,
        plan_version_id=plan.id,
        status=VerificationRunStatus.COMPLETE,
        tool_call_count=3,
    )
    await db.verification_runs.insert_one(run.model_dump(mode="python"))

    # Unrelated tool runs for the same snapshot that DO NOT belong to this run
    unrelated_tool = ToolRun(
        snapshot_id=snap.id,
        tool_name="search_code_lexical",
        input_hash="hash_unrelated",
        input_summary={"query": "other_query"},
        status=ToolRunStatus.SUCCEEDED,
        result_count=5,
        duration_ms=20,
    )
    await db.tool_runs.insert_one(unrelated_tool.model_dump(mode="python"))

    with TestClient(create_app(settings)) as client:
        res = client.get(f"/v1/verification-runs/{run.id}")
        assert res.status_code == 200
        body = res.json()
        # MUST explicitly report LEGACY_TRACE_UNAVAILABLE instead of returning snapshot's unrelated tools
        assert body["trace_attribution_status"] == "LEGACY_TRACE_UNAVAILABLE"
        assert len(body["tool_runs"]) == 0
        assert body["tool_execution_count"] == 0

    await mongo.close()


@pytest.mark.integration
async def test_human_decision_lifecycle_open_and_answered() -> None:
    settings = Settings()
    if not settings.mongo_is_configured:
        pytest.skip("MongoDB is required")
    mongo = MongoManager(settings)
    await mongo.connect()
    await ensure_indexes(mongo.database())
    db = mongo.database()

    account = f"auth-user-{new_id()[:6]}"
    inst_id = 88888
    now = datetime.now(UTC)

    # Session for account
    token = new_id()
    await db.github_sessions.insert_one(
        {
            "token_hash": hashlib.sha256(token.encode()).hexdigest(),
            "installation_id": inst_id,
            "account_login": account,
            "created_at": now,
            "expires_at": now + timedelta(days=1),
        }
    )
    cookie_val = _sign(token, settings.session_secret.get_secret_value())

    proj = Project(
        name=f"{account}/decision-repo",
        owner_id=account,
        repository_source_type=RepositorySourceType.GITHUB_APP,
        github_installation_id=inst_id,
        data_scope="USER",
    )
    await db.projects.insert_one(proj.model_dump(mode="python"))

    snap = RepositorySnapshot(
        project_id=proj.id,
        repository_identity=f"github:{proj.name}",
        requested_ref="main",
        resolved_commit_sha="998877665544",
        parser_version="v1",
        index_version="v1",
        status=SnapshotStatus.READY,
    )
    await db.repository_snapshots.insert_one(snap.model_dump(mode="python"))

    plan = PlanVersion(
        project_id=proj.id,
        version=1,
        change_request="Add dangerous payment pathway",
        candidate_plan="Payment steps",
    )
    await db.plan_versions.insert_one(plan.model_dump(mode="python"))

    ob = ProofObligation(
        project_id=proj.id,
        snapshot_id=snap.id,
        plan_version_id=plan.id,
        run_id="placeholder",
        statement="Payment route approved by VP Finance",
        normalized_statement="payment route approved by vp finance",
        category=ObligationCategory.BUSINESS_RULE,
        criticality="CRITICAL",
        status=ObligationStatus.HUMAN_REQUIRED,
    )
    await db.proof_obligations.insert_one(ob.model_dump(mode="python"))

    hq = HumanQuestion(
        run_id="placeholder",
        obligation_id=ob.id,
        question="Is VP Finance approval confirmed on SEC-99?",
        why_needed="Payment policy requires authorized business signoff.",
        authority_required="VP Finance",
        status=HumanQuestionStatus.OPEN,
    )
    await db.human_questions.insert_one(hq.model_dump(mode="python"))

    run = VerificationRun(
        project_id=proj.id,
        snapshot_id=snap.id,
        plan_version_id=plan.id,
        status=VerificationRunStatus.HUMAN_WAIT,
        open_human_question_ids=[hq.id],
    )
    await db.verification_runs.insert_one(run.model_dump(mode="python"))

    # Update placeholders
    await db.proof_obligations.update_one({"id": ob.id}, {"$set": {"run_id": run.id}})
    await db.human_questions.update_one({"id": hq.id}, {"$set": {"run_id": run.id}})

    with TestClient(create_app(settings)) as client:
        client.cookies.set("planproof_session", cookie_val)

        # 1. Inspect open question state
        res = client.get(f"/v1/verification-runs/{run.id}")
        assert res.status_code == 200
        run_data = res.json()
        assert run_data["run"]["status"] == "HUMAN_WAIT"
        assert len(run_data["human_questions"]) == 1
        assert run_data["human_questions"][0]["status"] == "OPEN"
        assert run_data["human_questions"][0]["answer"] is None

        # 2. Submit authorized answer
        ans_res = client.post(
            f"/v1/human-questions/{hq.id}/answers",
            json={"answer": "Approved by VP Finance on SEC-99.", "actor_id": account},
        )
        assert ans_res.status_code == 202

        # 3. Verify question is ANSWERED and run is queued for resumption
        res_after = client.get(f"/v1/verification-runs/{run.id}")
        assert res_after.status_code == 200
        after_data = res_after.json()
        assert len(after_data["human_questions"]) == 1
        hq_after = after_data["human_questions"][0]
        assert hq_after["status"] == "ANSWERED"
        assert hq_after["answer"] == "Approved by VP Finance on SEC-99."
        assert hq_after["answered_at"] is not None

        # 4. Attempting to submit a conflicting answer yields 409 Conflict
        conf_res = client.post(
            f"/v1/human-questions/{hq.id}/answers",
            json={"answer": "Conflicting answer rejected", "actor_id": "other-user"},
        )
        assert conf_res.status_code == 409

    await mongo.close()


@pytest.mark.integration
async def test_run_report_human_decision_state_and_evidence_snippets() -> None:
    settings = Settings()
    if not settings.mongo_is_configured:
        pytest.skip("MongoDB is required")
    mongo = MongoManager(settings)
    await mongo.connect()
    await ensure_indexes(mongo.database())
    db = mongo.database()

    # Set up project, snapshot, plan, run without cookies (test mode)
    proj = Project(
        name="test-org/repo",
        owner_id="test-org",
        repository_source_type=RepositorySourceType.PUBLIC_GITHUB,
        data_scope="USER",
    )
    await db.projects.insert_one(proj.model_dump(mode="python"))

    snap = RepositorySnapshot(
        project_id=proj.id,
        repository_identity="github:test-org/repo",
        requested_ref="main",
        resolved_commit_sha="deadbeef1234",
        parser_version="v1",
        index_version="v1",
        status=SnapshotStatus.READY,
    )
    await db.repository_snapshots.insert_one(snap.model_dump(mode="python"))

    # Add repository file for immutable snippet reconstruction
    await db.repository_files.insert_one(
        {
            "snapshot_id": snap.id,
            "path": "src/ledger.ts",
            "content_hash": "hash-ledger-123",
            "text": "line 1\nexport const ledgerEntry = true;\nline 3\nline 4\n",
        }
    )

    plan = PlanVersion(
        project_id=proj.id,
        version=1,
        change_request="Add ledger check",
        candidate_plan="Plan text",
    )
    await db.plan_versions.insert_one(plan.model_dump(mode="python"))

    run = VerificationRun(
        project_id=proj.id,
        snapshot_id=snap.id,
        plan_version_id=plan.id,
        status=VerificationRunStatus.COMPLETE,
        tool_call_count=1,
    )
    await db.verification_runs.insert_one(run.model_dump(mode="python"))

    # Tool run stamped with run_id
    tool = ToolRun(
        snapshot_id=snap.id,
        run_id=run.id,
        tool_name="search_code_lexical",
        input_hash="hash1",
        input_summary={"query": "ledgerEntry", "path": "src/ledger.ts"},
        status=ToolRunStatus.SUCCEEDED,
        result_count=1,
        duration_ms=15,
    )
    await db.tool_runs.insert_one(tool.model_dump(mode="python"))

    # Evidence created
    evidence = Evidence(
        snapshot_id=snap.id,
        source_tool_run_id=tool.id,
        evidence_type=EvidenceType.SOURCE_RANGE,
        path="src/ledger.ts",
        line_start=2,
        line_end=2,
        content_hash="hash-ledger-123",
        summary="Found ledgerEntry definition.",
    )
    await db.evidence.insert_one(evidence.model_dump(mode="python"))

    # Obligation attached to run and evidence
    ob = ProofObligation(
        project_id=proj.id,
        snapshot_id=snap.id,
        plan_version_id=plan.id,
        run_id=run.id,
        statement="Ledger entry exists",
        normalized_statement="ledger entry exists",
        category=ObligationCategory.BEHAVIOR,
        criticality="HIGH",
        status=ObligationStatus.VERIFIED,
        evidence_ids=[evidence.id],
    )
    await db.proof_obligations.insert_one(ob.model_dump(mode="python"))

    # Resolved Human Question
    answered_at = datetime.now(UTC)
    hq = HumanQuestion(
        run_id=run.id,
        obligation_id=ob.id,
        question="Is ledger modification allowed?",
        why_needed="Compliance requirement.",
        authority_required="Security team",
        status=HumanQuestionStatus.ANSWERED,
        answer="Approved by compliance lead on ticket SEC-401.",
        actor_id="sec-lead",
        answered_at=answered_at,
    )
    await db.human_questions.insert_one(hq.model_dump(mode="python"))

    with TestClient(create_app(settings)) as client:
        # 1. Test get_verification_run returns answer and answered_at
        res = client.get(f"/v1/verification-runs/{run.id}")
        assert res.status_code == 200
        body = res.json()
        assert body["trace_attribution_status"] == "EXACT"
        assert len(body["tool_runs"]) == 1
        assert body["tool_runs"][0]["input_summary"]["query"] == "ledgerEntry"
        assert body["evidence_count"] == 1
        assert len(body["human_questions"]) == 1
        hq_res = body["human_questions"][0]
        assert hq_res["status"] == "ANSWERED"
        assert hq_res["answer"] == "Approved by compliance lead on ticket SEC-401."
        assert hq_res["answered_at"] is not None

        # 2. Test list_run_evidence returns snippet from immutable repository_files
        res_ev = client.get(f"/v1/verification-runs/{run.id}/evidence")
        assert res_ev.status_code == 200
        ev_list = res_ev.json()
        assert len(ev_list) == 1
        assert ev_list[0]["snippet"] == "export const ledgerEntry = true;"
        assert ev_list[0]["relationship"] == "SUPPORTS"
        assert ev_list[0]["obligation_id"] == ob.id

    await mongo.close()

