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
        assert await mongo.database().events.count_documents({"run_id": run.id}) == 2
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
