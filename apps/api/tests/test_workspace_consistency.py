import hashlib
import hmac
from datetime import UTC, datetime, timedelta

import pytest
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
from app.repositories.runs import RunRepository
from app.repositories.verification import VerificationRepository
from app.workflow.engine import VerificationWorkflow


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
        res_psnap = client.get(
            f"/v1/projects/{proj1.id}/snapshots", cookies={"planproof_session": cookie2}
        )
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
        res_snap_auth = client.get(
            f"/v1/snapshots/{snap1.id}", cookies={"planproof_session": cookie1}
        )
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


@pytest.mark.integration
async def test_real_investigation_workflow_executes_tools_and_mints_evidence() -> None:
    settings = Settings()
    if not settings.mongo_is_configured:
        pytest.skip("MongoDB is required")
    mongo = MongoManager(settings)
    await mongo.connect()
    await ensure_indexes(mongo.database())
    db = mongo.database()

    proj = Project(
        name="test-org/investigation-repo",
        owner_id="test-investigator",
        repository_source_type=RepositorySourceType.PUBLIC_GITHUB,
        github_installation_id=98765,
        data_scope="USER",
    )
    await db.projects.insert_one(proj.model_dump(mode="python"))

    snap = RepositorySnapshot(
        project_id=proj.id,
        repository_identity="test-org/investigation-repo",
        parser_version="v1",
        index_version="v1",
        status=SnapshotStatus.READY,
        resolved_commit_sha="a1b2c3d4e5f6",
    )
    await db.repository_snapshots.insert_one(snap.model_dump(mode="python"))

    routes_text = "import express from 'express';\nexport const router = express.Router();\nrouter.get('/history', getHistory);"
    convo_text = "import mongoose, { Schema } from 'mongoose';\nconst ConversationSchema = new Schema({ userId: String, messages: Array });\nexport const Conversation = mongoose.model('Conversation', ConversationSchema);"

    # Seed files into repository_files with authentic sha256 content hashes
    await db.repository_files.insert_one(
        {
            "snapshot_id": snap.id,
            "path": "src/api/routes.ts",
            "language": "typescript",
            "size_bytes": len(routes_text.encode()),
            "content_hash": hashlib.sha256(routes_text.encode()).hexdigest(),
            "text": routes_text,
        }
    )
    await db.repository_files.insert_one(
        {
            "snapshot_id": snap.id,
            "path": "src/models/conversation.ts",
            "language": "typescript",
            "size_bytes": len(convo_text.encode()),
            "content_hash": hashlib.sha256(convo_text.encode()).hexdigest(),
            "text": convo_text,
        }
    )

    plan = PlanVersion(
        project_id=proj.id,
        version=1,
        change_request="Add conversation history to the API",
        candidate_plan="Use existing mongoose database model and express router",
    )
    await db.plan_versions.insert_one(plan.model_dump(mode="python"))

    run = VerificationRun(
        project_id=proj.id,
        snapshot_id=snap.id,
        plan_version_id=plan.id,
        status=VerificationRunStatus.QUEUED,
    )
    await db.verification_runs.insert_one(run.model_dump(mode="python"))

    # Create 3 obligations:
    # 1. Code-verifiable matching MongoDB / mongoose
    ob1 = ProofObligation(
        project_id=proj.id,
        snapshot_id=snap.id,
        plan_version_id=plan.id,
        run_id=run.id,
        statement="Use existing mongoose model and database persistence schema",
        normalized_statement="use existing mongoose model and database persistence schema",
        category=ObligationCategory.SCHEMA,
        criticality="HIGH",
        verification_hints=["mongoose", "Schema"],
    )
    # 2. Code-verifiable with no matching code in repository
    ob2 = ProofObligation(
        project_id=proj.id,
        snapshot_id=snap.id,
        plan_version_id=plan.id,
        run_id=run.id,
        statement="Use existing gRPC protobuf client for billing synchronization",
        normalized_statement="use existing grpc protobuf client for billing synchronization",
        category=ObligationCategory.DEPENDENCY,
        criticality="MEDIUM",
        verification_hints=["grpc_client_proto_v2"],
    )
    # 3. Business rule requiring human authority
    ob3 = ProofObligation(
        project_id=proj.id,
        snapshot_id=snap.id,
        plan_version_id=plan.id,
        run_id=run.id,
        statement="Conversation history must be deleted automatically after 30 days",
        normalized_statement="conversation history must be deleted automatically after 30 days",
        category=ObligationCategory.BUSINESS_RULE,
        criticality="CRITICAL",
    )

    await db.proof_obligations.insert_one(ob1.model_dump(mode="python"))
    await db.proof_obligations.insert_one(ob2.model_dump(mode="python"))
    await db.proof_obligations.insert_one(ob3.model_dump(mode="python"))

    runs = RunRepository(mongo)
    verification = VerificationRepository(mongo)

    # Run workflow
    workflow = VerificationWorkflow(runs, verification, settings)
    await workflow.run(run.id)

    # Reload run and obligations
    updated_run = await runs.get_run(run.id)
    u_ob1 = await verification.get_obligation(ob1.id)
    u_ob2 = await verification.get_obligation(ob2.id)
    u_ob3 = await verification.get_obligation(ob3.id)

    # 1. Code matching obligation is VERIFIED with server-issued evidence
    assert u_ob1.status == ObligationStatus.VERIFIED
    assert len(u_ob1.evidence_ids) >= 1
    ev_doc = await db.evidence.find_one({"id": u_ob1.evidence_ids[0]})
    assert ev_doc is not None
    assert ev_doc["snapshot_id"] == snap.id
    assert ev_doc["path"] == "src/models/conversation.ts"

    # 2. Non-matching obligation is INCONCLUSIVE with truthful explanation
    assert u_ob2.status == ObligationStatus.INCONCLUSIVE
    assert "inconclusive_reason" in u_ob2.proposal_metadata

    # 3. Business rule is HUMAN_REQUIRED and run is paused at HUMAN_WAIT
    assert u_ob3.status == ObligationStatus.HUMAN_REQUIRED
    assert updated_run.status == VerificationRunStatus.HUMAN_WAIT
    assert len(updated_run.open_human_question_ids) == 1

    # 4. Tool runs are stamped with exact run_id
    tool_runs = [item async for item in db.tool_runs.find({"run_id": run.id})]
    assert len(tool_runs) >= 2
    for tr in tool_runs:
        assert tr["run_id"] == run.id
        assert tr["snapshot_id"] == snap.id

    await mongo.close()


@pytest.mark.integration
async def test_deterministic_relevance_guard_prevents_false_positive() -> None:
    """Regression test: Unrelated match (e.g. auth in App.tsx) must not verify a ChatInterface claim."""
    settings = Settings()
    if not settings.mongo_is_configured:
        pytest.skip("MongoDB is required")
    mongo = MongoManager(settings)
    await mongo.connect()
    await ensure_indexes(mongo.database())
    db = mongo.database()

    user = f"rel-test-{new_id()[:6]}"
    proj = Project(
        name=f"{user}/averix-test",
        owner_id=user,
        repository_source_type=RepositorySourceType.GITHUB_APP,
        data_scope="USER",
    )
    await db.projects.insert_one(proj.model_dump(mode="python"))

    snap = RepositorySnapshot(
        project_id=proj.id,
        repository_identity=f"github:{proj.name}",
        requested_ref="main",
        resolved_commit_sha="aabbcc112233",
        parser_version="v1",
        index_version="v1",
        status=SnapshotStatus.READY,
    )
    await db.repository_snapshots.insert_one(snap.model_dump(mode="python"))

    # File 1: Only PrivyProvider in App.tsx (no ChatInterface, no sendMessageToAgent)
    app_tsx = """import { PrivyProvider } from '@privy-io/react-auth';
import Index from "./pages/Index";
"""
    await db.repository_files.insert_one(
        {
            "snapshot_id": snap.id,
            "path": "src/App.tsx",
            "content_hash": hashlib.sha256(app_tsx.encode()).hexdigest(),
            "text": app_tsx,
            "symbols": [],
        }
    )

    plan = PlanVersion(
        project_id=proj.id,
        version=1,
        change_request="Add agent client",
        candidate_plan="Implement ChatInterface and sendMessageToAgent",
    )
    await db.plan_versions.insert_one(plan.model_dump(mode="python"))

    run = VerificationRun(
        project_id=proj.id,
        snapshot_id=snap.id,
        plan_version_id=plan.id,
        status=VerificationRunStatus.QUEUED,
    )
    await db.verification_runs.insert_one(run.model_dump(mode="python"))

    ob = ProofObligation(
        project_id=proj.id,
        snapshot_id=snap.id,
        plan_version_id=plan.id,
        run_id=run.id,
        statement="ChatInterface component must import sendMessageToAgent from '@/utils/arbitrumAgent' to process user input commands.",
        normalized_statement="chatinterface component must import sendmessagetoagent from '@/utils/arbitrumagent' to process user input commands.",
        category=ObligationCategory.DEPENDENCY,
        criticality="HIGH",
    )
    await db.proof_obligations.insert_one(ob.model_dump(mode="python"))

    runs = RunRepository(mongo)
    verification = VerificationRepository(mongo)
    workflow = VerificationWorkflow(runs, verification, settings)
    await workflow.run(run.id)

    # Reload obligation: MUST BE INCONCLUSIVE (not falsely VERIFIED by App.tsx)
    u_ob = await verification.get_obligation(ob.id)
    assert u_ob.status == ObligationStatus.INCONCLUSIVE
    assert len(u_ob.evidence_ids) == 0

    await mongo.close()


@pytest.mark.integration
async def test_cross_obligation_evidence_isolation() -> None:
    """Test that evidence minted for Obligation A is isolated and never affects Obligation B."""
    settings = Settings()
    if not settings.mongo_is_configured:
        pytest.skip("MongoDB is required")
    mongo = MongoManager(settings)
    await mongo.connect()
    await ensure_indexes(mongo.database())
    db = mongo.database()

    user = f"iso-test-{new_id()[:6]}"
    proj = Project(
        name=f"{user}/multi-ob-test",
        owner_id=user,
        repository_source_type=RepositorySourceType.GITHUB_APP,
        data_scope="USER",
    )
    await db.projects.insert_one(proj.model_dump(mode="python"))

    snap = RepositorySnapshot(
        project_id=proj.id,
        repository_identity=f"github:{proj.name}",
        requested_ref="main",
        resolved_commit_sha="aabbcc445566",
        parser_version="v1",
        index_version="v1",
        status=SnapshotStatus.READY,
    )
    await db.repository_snapshots.insert_one(snap.model_dump(mode="python"))

    # File only satisfying obligation A
    chat_file = """import { sendMessageToAgent } from '@/utils/arbitrumAgent';
export function ChatInterface() {
    return <div>Chat</div>;
}
"""
    await db.repository_files.insert_one(
        {
            "snapshot_id": snap.id,
            "path": "src/components/ChatInterface.tsx",
            "content_hash": hashlib.sha256(chat_file.encode()).hexdigest(),
            "text": chat_file,
            "symbols": [],
        }
    )

    plan = PlanVersion(
        project_id=proj.id,
        version=1,
        change_request="Multi claim plan",
        candidate_plan="Claim A and Claim B",
    )
    await db.plan_versions.insert_one(plan.model_dump(mode="python"))

    run = VerificationRun(
        project_id=proj.id,
        snapshot_id=snap.id,
        plan_version_id=plan.id,
        status=VerificationRunStatus.QUEUED,
    )
    await db.verification_runs.insert_one(run.model_dump(mode="python"))

    ob_a = ProofObligation(
        project_id=proj.id,
        snapshot_id=snap.id,
        plan_version_id=plan.id,
        run_id=run.id,
        statement="ChatInterface component imports sendMessageToAgent from '@/utils/arbitrumAgent'",
        normalized_statement="chatinterface component imports sendmessagetoagent from '@/utils/arbitrumagent'",
        category=ObligationCategory.DEPENDENCY,
        criticality="HIGH",
    )
    ob_b = ProofObligation(
        project_id=proj.id,
        snapshot_id=snap.id,
        plan_version_id=plan.id,
        run_id=run.id,
        statement="Database schema defines user_balance integer column with unique constraint",
        normalized_statement="database schema defines user_balance integer column with unique constraint",
        category=ObligationCategory.SCHEMA,
        criticality="HIGH",
    )
    await db.proof_obligations.insert_one(ob_a.model_dump(mode="python"))
    await db.proof_obligations.insert_one(ob_b.model_dump(mode="python"))

    runs = RunRepository(mongo)
    verification = VerificationRepository(mongo)
    workflow = VerificationWorkflow(runs, verification, settings)
    await workflow.run(run.id)

    u_ob_a = await verification.get_obligation(ob_a.id)
    u_ob_b = await verification.get_obligation(ob_b.id)

    # Obligation A is VERIFIED with exact evidence
    assert u_ob_a.status == ObligationStatus.VERIFIED
    assert len(u_ob_a.evidence_ids) == 1

    # Obligation B is INCONCLUSIVE with 0 evidence (isolated)
    assert u_ob_b.status == ObligationStatus.INCONCLUSIVE
    assert len(u_ob_b.evidence_ids) == 0

    await mongo.close()


@pytest.mark.integration
async def test_evidence_sufficiency_regression_suite_a_through_g() -> None:
    """Test full regression scenarios A through G for evidence sufficiency, call-sites, and classification."""
    settings = Settings(verification_max_iterations=20)
    if not settings.mongo_is_configured:
        pytest.skip("MongoDB is required")
    mongo = MongoManager(settings)
    await mongo.connect()
    await ensure_indexes(mongo.database())
    db = mongo.database()

    user = f"suff-test-{new_id()[:6]}"
    proj = Project(
        name=f"{user}/averix-sufficiency-test",
        owner_id=user,
        repository_source_type=RepositorySourceType.GITHUB_APP,
        data_scope="USER",
    )
    await db.projects.insert_one(proj.model_dump(mode="python"))

    snap = RepositorySnapshot(
        project_id=proj.id,
        repository_identity=f"github:{proj.name}",
        requested_ref="main",
        resolved_commit_sha="cc9988771122",
        parser_version="v1",
        index_version="v1",
        status=SnapshotStatus.READY,
    )
    await db.repository_snapshots.insert_one(snap.model_dump(mode="python"))

    # ChatInterface file with import and call site
    chat_file_with_call = """import React, { useState } from 'react';
import { sendMessageToAgent } from '@/utils/arbitrumAgent';

export function ChatInterface() {
    const [input, setInput] = useState('');
    const handleSubmit = async () => {
        const res = await sendMessageToAgent(input);
        console.log(res);
    };
    return <button onClick={handleSubmit}>Send</button>;
}
"""
    # App.tsx with import and provider wrapping
    app_file = """import React from 'react';
import { PrivyProvider } from '@privy-io/react-auth';
import Index from "./pages/Index";

export default function App() {
    return (
        <PrivyProvider appId="test-app-id">
            <Index />
        </PrivyProvider>
    );
}
"""
    await db.repository_files.insert_one(
        {
            "snapshot_id": snap.id,
            "path": "src/components/ChatInterface.tsx",
            "content_hash": hashlib.sha256(chat_file_with_call.encode()).hexdigest(),
            "text": chat_file_with_call,
            "symbols": [],
        }
    )
    await db.repository_files.insert_one(
        {
            "snapshot_id": snap.id,
            "path": "src/App.tsx",
            "content_hash": hashlib.sha256(app_file.encode()).hexdigest(),
            "text": app_file,
            "symbols": [],
        }
    )

    plan = PlanVersion(
        project_id=proj.id,
        version=1,
        change_request="Sufficiency regression test plan",
        candidate_plan="Validate claims A through G",
    )
    await db.plan_versions.insert_one(plan.model_dump(mode="python"))

    run = VerificationRun(
        project_id=proj.id,
        snapshot_id=snap.id,
        plan_version_id=plan.id,
        status=VerificationRunStatus.QUEUED,
    )
    await db.verification_runs.insert_one(run.model_dump(mode="python"))

    # Scenario A: Import claim with import snippet present -> VERIFIED
    ob_a = ProofObligation(
        project_id=proj.id,
        snapshot_id=snap.id,
        plan_version_id=plan.id,
        run_id=run.id,
        statement="ChatInterface imports sendMessageToAgent from '@/utils/arbitrumAgent'",
        normalized_statement="chatinterface imports sendmessagetoagent from '@/utils/arbitrumagent'",
        category=ObligationCategory.DEPENDENCY,
        criticality="HIGH",
    )

    # Scenario B: Broader qualitative behavior with import present -> NOT VERIFIED (INCONCLUSIVE)
    ob_b = ProofObligation(
        project_id=proj.id,
        snapshot_id=snap.id,
        plan_version_id=plan.id,
        run_id=run.id,
        statement="sendMessageToAgent communication is correctly implemented and reliable.",
        normalized_statement="sendmessagetoagent communication is correctly implemented and reliable.",
        category=ObligationCategory.BEHAVIOR,
        criticality="HIGH",
    )

    # Scenario C: Call site claim with actual invocation present -> VERIFIED
    ob_c = ProofObligation(
        project_id=proj.id,
        snapshot_id=snap.id,
        plan_version_id=plan.id,
        run_id=run.id,
        statement="ChatInterface invokes sendMessageToAgent",
        normalized_statement="chatinterface invokes sendmessagetoagent",
        category=ObligationCategory.BEHAVIOR,
        criticality="HIGH",
    )

    # Scenario D: Privy import claim -> VERIFIED
    ob_d = ProofObligation(
        project_id=proj.id,
        snapshot_id=snap.id,
        plan_version_id=plan.id,
        run_id=run.id,
        statement="App imports PrivyProvider from '@privy-io/react-auth'",
        normalized_statement="app imports privyprovider from '@privy-io/react-auth'",
        category=ObligationCategory.DEPENDENCY,
        criticality="HIGH",
    )

    # Scenario E: Security overclaim -> NOT VERIFIED (INCONCLUSIVE)
    ob_e = ProofObligation(
        project_id=proj.id,
        snapshot_id=snap.id,
        plan_version_id=plan.id,
        run_id=run.id,
        statement="PrivyProvider secures the application.",
        normalized_statement="privyprovider secures the application.",
        category=ObligationCategory.BEHAVIOR,
        criticality="HIGH",
    )

    # Scenario F: Nonexistent technical identifier -> INCONCLUSIVE (not HUMAN_REQUIRED)
    ob_f = ProofObligation(
        project_id=proj.id,
        snapshot_id=snap.id,
        plan_version_id=plan.id,
        run_id=run.id,
        statement="Billing synchronization must be configured correctly for unsupportedNonExistentServiceIdentifierV99",
        normalized_statement="billing synchronization must be configured correctly for unsupportednonexistentserviceidentifierv99",
        category=ObligationCategory.DEPENDENCY,
        criticality="MEDIUM",
    )

    # Scenario G: Genuine business rule -> HUMAN_REQUIRED / HUMAN_WAIT
    ob_g = ProofObligation(
        project_id=proj.id,
        snapshot_id=snap.id,
        plan_version_id=plan.id,
        run_id=run.id,
        statement="Conversation history must be retained for 30 days.",
        normalized_statement="conversation history must be retained for 30 days.",
        category=ObligationCategory.BUSINESS_RULE,
        criticality="CRITICAL",
    )

    for ob in [ob_a, ob_b, ob_c, ob_d, ob_e, ob_f, ob_g]:
        await db.proof_obligations.insert_one(ob.model_dump(mode="python"))

    runs = RunRepository(mongo)
    verification = VerificationRepository(mongo)
    workflow = VerificationWorkflow(runs, verification, settings)
    await workflow.run(run.id)

    res_a = await verification.get_obligation(ob_a.id)
    res_b = await verification.get_obligation(ob_b.id)
    res_c = await verification.get_obligation(ob_c.id)
    res_d = await verification.get_obligation(ob_d.id)
    res_e = await verification.get_obligation(ob_e.id)
    res_f = await verification.get_obligation(ob_f.id)
    res_g = await verification.get_obligation(ob_g.id)
    updated_run = await runs.get_run(run.id)

    # A: Exact import claim -> VERIFIED
    assert res_a.status == ObligationStatus.VERIFIED
    assert len(res_a.evidence_ids) >= 1

    # B: Broader qualitative claim -> INCONCLUSIVE (NOT VERIFIED)
    assert res_b.status == ObligationStatus.INCONCLUSIVE

    # C: Call site claim -> VERIFIED
    assert res_c.status == ObligationStatus.VERIFIED
    assert len(res_c.evidence_ids) >= 1

    # D: Exact Privy import claim -> VERIFIED
    assert res_d.status == ObligationStatus.VERIFIED
    assert len(res_d.evidence_ids) >= 1

    # E: Security overclaim -> INCONCLUSIVE (NOT VERIFIED)
    assert res_e.status == ObligationStatus.INCONCLUSIVE

    # F: Missing technical identifier -> INCONCLUSIVE (NOT HUMAN_REQUIRED)
    assert res_f.status == ObligationStatus.INCONCLUSIVE

    # G: Genuine business rule -> HUMAN_REQUIRED
    assert res_g.status == ObligationStatus.HUMAN_REQUIRED

    # Run overall gate reflects HUMAN_WAIT due to ob_g
    assert updated_run.status == VerificationRunStatus.HUMAN_WAIT
    assert len(updated_run.open_human_question_ids) == 1

    await mongo.close()
