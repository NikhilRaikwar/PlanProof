from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.db.indexes import ensure_indexes
from app.db.mongo import MongoManager
from app.domain.projects import CreateProjectRequest, Project, RepositorySourceType
from app.domain.runs import (
    HumanQuestionStatus,
    PlanVersion,
    RepositorySnapshot,
    SnapshotStatus,
    VerificationRun,
    VerificationRunStatus,
)
from app.domain.verification import (
    Criticality,
    ObligationCategory,
    ObligationStatus,
    ProofObligation,
)
from app.ingestion.service import INDEX_VERSION, PARSER_VERSION, SnapshotIngestionService
from app.ingestion.sources import seeded_fixture_source
from app.repositories.projects import ProjectsRepository
from app.repositories.runs import RunRepository
from app.repositories.verification import VerificationRepository
from app.workflow.engine import VerificationWorkflow


@pytest.mark.integration
async def test_human_wait_restart_resume_preserves_disproved_gate() -> None:
    settings = Settings()
    if not settings.mongo_is_configured:
        pytest.skip("MongoDB is required")
    mongo = MongoManager(settings)
    await mongo.connect()
    await ensure_indexes(mongo.database())
    project = snapshot = plan = run = question = None
    try:
        project = Project.from_create_request(
            CreateProjectRequest(
                name="workflow",
                owner_id=f"workflow-{uuid4().hex}",
                repository_source_type=RepositorySourceType.SEEDED,
                fixture_id="partial-refunds-v1",
            )
        )
        await ProjectsRepository(mongo).create(project)
        snapshot = RepositorySnapshot(
            project_id=project.id,
            repository_identity=f"fixture:{uuid4().hex}",
            parser_version="test",
            index_version="test",
            status=SnapshotStatus.READY,
        )
        plan = PlanVersion(
            project_id=project.id,
            version=1,
            change_request="refunds",
            candidate_plan="Support partial refunds and confirm reporting impact",
        )
        runs = RunRepository(mongo)
        await runs.create_snapshot(snapshot)
        await runs.create_plan_version(plan)
        run = VerificationRun(
            project_id=project.id, snapshot_id=snapshot.id, plan_version_id=plan.id
        )
        await runs.create_run(run)
        verification = VerificationRepository(mongo)
        disproved = ProofObligation(
            project_id=project.id,
            snapshot_id=snapshot.id,
            plan_version_id=plan.id,
            run_id=run.id,
            statement="Refund amount is a string",
            normalized_statement="refund amount is a string",
            category=ObligationCategory.SCHEMA,
            criticality=Criticality.HIGH,
            status=ObligationStatus.DISPROVED,
        )
        human = ProofObligation(
            project_id=project.id,
            snapshot_id=snapshot.id,
            plan_version_id=plan.id,
            run_id=run.id,
            statement="Reporting accepts aggregation changes",
            normalized_statement="reporting accepts aggregation changes",
            category=ObligationCategory.BUSINESS_RULE,
            criticality=Criticality.CRITICAL,
        )
        await verification.create_obligation(disproved)
        await verification.create_obligation(human)
        await VerificationWorkflow(runs, verification, settings).run(run.id)
        waiting = await runs.get_run(run.id)
        assert waiting.status == "HUMAN_WAIT" and len(waiting.open_human_question_ids) == 1
        question = await runs.get_question(waiting.open_human_question_ids[0])
        await mongo.close()
        mongo = MongoManager(settings)
        await mongo.connect()
        runs, verification = RunRepository(mongo), VerificationRepository(mongo)
        reloaded = await runs.get_run(run.id)
        assert reloaded.status == "HUMAN_WAIT"
        question = await runs.get_question(question.id)
        question.status, question.answer, question.actor_id = (
            HumanQuestionStatus.ANSWERED,
            "Approved by finance",
            "finance-owner",
        )
        await runs.update_question(question)
        human = await verification.get_obligation(human.id)
        human.status = ObligationStatus.VERIFIED
        await verification.update_obligation(human)
        reloaded.status = VerificationRunStatus.QUEUED
        reloaded.open_human_question_ids = []
        await runs.update_run(reloaded)
        await VerificationWorkflow(runs, verification, settings).run(run.id)
        final = await runs.get_run(run.id)
        assert final.status == "BLOCKED"
        await VerificationWorkflow(runs, verification, settings).run(run.id)
        assert (await runs.get_run(run.id)).status == "BLOCKED"
        assert await mongo.database().events.count_documents({"run_id": run.id}) >= 2
    finally:
        database = mongo.database()
        if run:
            await database.events.delete_many({"run_id": run.id})
            await database.human_questions.delete_many({"run_id": run.id})
            await database.verification_runs.delete_one({"id": run.id})
        if plan:
            await database.proof_obligations.delete_many({"plan_version_id": plan.id})
            await database.plan_versions.delete_one({"id": plan.id})
        if snapshot:
            await database.repository_snapshots.delete_one({"id": snapshot.id})
        if project:
            await database.projects.delete_one({"id": project.id})
        await mongo.close()


@pytest.mark.integration
async def test_seeded_obligations_get_real_evidence_and_mixed_outcomes() -> None:
    settings = Settings()
    if not settings.mongo_is_configured:
        pytest.skip("MongoDB is required")
    mongo = MongoManager(settings)
    await mongo.connect()
    project = snapshot = plan = run = None
    try:
        project = Project.from_create_request(
            CreateProjectRequest(
                name="seeded mixed",
                owner_id=f"seeded-{uuid4().hex}",
                repository_source_type=RepositorySourceType.SEEDED,
                fixture_id="partial-refunds-v1",
            )
        )
        await ProjectsRepository(mongo).create(project)
        runs = RunRepository(mongo)
        source = seeded_fixture_source(
            "partial-refunds-v1", Path(__file__).resolve().parents[3] / "demo-repos"
        )
        snapshot = RepositorySnapshot(
            project_id=project.id,
            repository_identity=source.identity,
            parser_version=PARSER_VERSION,
            index_version=INDEX_VERSION,
        )
        await runs.create_snapshot(snapshot)
        snapshot = await SnapshotIngestionService(runs).ingest(snapshot.id, source)
        plan = PlanVersion(
            project_id=project.id,
            version=1,
            change_request="partial refunds",
            candidate_plan=(
                "Provider accepts amount; multiple refunds need no migration; "
                "billing unaffected; mobile impact known."
            ),
        )
        await runs.create_plan_version(plan)
        run = VerificationRun(
            project_id=project.id, snapshot_id=snapshot.id, plan_version_id=plan.id
        )
        await runs.create_run(run)
        verification = VerificationRepository(mongo)
        for statement, category in [
            ("Provider accepts a refund amount", ObligationCategory.BEHAVIOR),
            ("Multiple refunds fit current schema without migration", ObligationCategory.SCHEMA),
            ("Billing ledger is unaffected", ObligationCategory.BEHAVIOR),
            ("Mobile client impact is known", ObligationCategory.CROSS_SERVICE),
        ]:
            item = ProofObligation(
                project_id=project.id,
                snapshot_id=snapshot.id,
                plan_version_id=plan.id,
                run_id=run.id,
                statement=statement,
                normalized_statement=statement.casefold(),
                category=category,
                criticality=Criticality.HIGH,
            )
            await verification.create_obligation(item)
        await VerificationWorkflow(runs, verification, settings).run(run.id)
        current = await runs.get_run(run.id)
        statuses = {item.status for item in await verification.list_run_obligations(run.id)}
        assert current.status == "HUMAN_WAIT"
        assert ObligationStatus.VERIFIED in statuses
        assert ObligationStatus.DISPROVED in statuses
        assert ObligationStatus.HUMAN_REQUIRED in statuses
        assert await mongo.database().evidence.count_documents({"snapshot_id": snapshot.id}) >= 3
    finally:
        db = mongo.database()
        if run:
            await db.events.delete_many({"run_id": run.id})
            await db.human_questions.delete_many({"run_id": run.id})
            await db.verification_runs.delete_one({"id": run.id})
        if plan:
            await db.proof_obligations.delete_many({"plan_version_id": plan.id})
            await db.plan_versions.delete_one({"id": plan.id})
        if snapshot:
            await db.evidence.delete_many({"snapshot_id": snapshot.id})
            await db.tool_runs.delete_many({"snapshot_id": snapshot.id})
            await db.repository_files.delete_many({"snapshot_id": snapshot.id})
            await db.code_symbols.delete_many({"snapshot_id": snapshot.id})
            await db.repository_snapshots.delete_one({"id": snapshot.id})
        if project:
            await db.projects.delete_one({"id": project.id})
        await mongo.close()
