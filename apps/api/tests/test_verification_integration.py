from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.db.indexes import ensure_indexes
from app.db.mongo import MongoManager
from app.domain.projects import CreateProjectRequest, Project, RepositorySourceType
from app.domain.runs import RepositorySnapshot
from app.domain.verification import Criticality, ModelCall, ObligationCategory, ProofObligation
from app.ingestion.service import INDEX_VERSION, PARSER_VERSION, SnapshotIngestionService
from app.ingestion.sources import seeded_fixture_source
from app.repositories.projects import ProjectsRepository
from app.repositories.runs import RunRepository
from app.repositories.verification import VerificationRepository
from app.services.evidence import EvidenceAuthority, validate_source_contains
from app.services.models import ProviderGateway
from app.services.obligations import ObligationExtractionService
from app.services.repository_tools import ReadFileRangeInput, RepositoryTools


@pytest.mark.integration
async def test_seeded_tool_evidence_validator_and_reconnect_slice() -> None:
    settings = Settings()
    if not settings.mongo_is_configured:
        pytest.skip("MONGODB_URI is not configured")
    mongo = MongoManager(settings)
    await mongo.connect()
    await ensure_indexes(mongo.database())
    owner = f"verify-itest-{uuid4().hex}"
    project = snapshot = None
    evidence_id = tool_run_id = model_call_id = obligation_id = None
    try:
        project = Project.from_create_request(
            CreateProjectRequest(
                name="verification slice",
                owner_id=owner,
                repository_source_type=RepositorySourceType.SEEDED,
                fixture_id="partial-refunds-v1",
            )
        )
        await ProjectsRepository(mongo).create(project)
        source = seeded_fixture_source(
            "partial-refunds-v1", Path(__file__).resolve().parents[3] / "demo-repos"
        )
        snapshot = RepositorySnapshot(
            project_id=project.id,
            repository_identity=source.identity,
            source_type=source.source_type,
            requested_ref=source.requested_ref,
            parser_version=PARSER_VERSION,
            index_version=INDEX_VERSION,
        )
        runs = RunRepository(mongo)
        await runs.create_snapshot(snapshot)
        snapshot = await SnapshotIngestionService(runs).ingest(snapshot.id, source)
        verification = VerificationRepository(mongo)
        tools = RepositoryTools(runs, verification)
        source_range = await tools.read_file_range(
            ReadFileRangeInput(
                snapshot_id=snapshot.id, path="db/models/refund.ts", start_line=8, end_line=10
            )
        )
        tool_doc = await mongo.database().tool_runs.find_one(
            {"snapshot_id": snapshot.id, "tool_name": "read_file_range"}, sort=[("started_at", -1)]
        )
        tool_run_id = tool_doc["id"]
        evidence = await EvidenceAuthority(verification).issue_source_range(
            snapshot_id=snapshot.id,
            tool_run_id=tool_run_id,
            path=source_range["path"],
            line_start=8,
            line_end=10,
            summary="payment_id has a supported unique constraint",
        )
        evidence_id = evidence.id
        assert (await EvidenceAuthority(verification).validate(evidence.id)).id == evidence.id
        supported = await validate_source_contains(
            verification, snapshot.id, "db/models/refund.ts", "unique: true"
        )
        contradicted = await validate_source_contains(
            verification, snapshot.id, "db/models/refund.ts", "amount!: string"
        )
        obligation = await verification.create_obligation(
            ProofObligation(
                project_id=project.id,
                snapshot_id=snapshot.id,
                plan_version_id=f"pv-{uuid4().hex}",
                statement="Refund amount is stored as a string",
                normalized_statement="refund amount is stored as a string",
                category=ObligationCategory.SCHEMA,
                criticality=Criticality.HIGH,
            )
        )
        obligation_id = obligation.id
        model_call = await verification.create_model_call(
            ModelCall(
                provider="integration",
                model="deterministic",
                request_schema_version="v1",
                response_schema_version="v1",
                latency_ms=1,
                retry_count=0,
            )
        )
        model_call_id = model_call.id
        await mongo.close()
        mongo = MongoManager(settings)
        await mongo.connect()
        assert await mongo.database().tool_runs.find_one({"id": tool_run_id})
        assert await mongo.database().evidence.find_one({"id": evidence_id})
        assert await mongo.database().model_calls.find_one({"id": model_call_id})
        assert await mongo.database().proof_obligations.find_one({"id": obligation_id})
        print(
            "VERIFY_SLICE",
            {
                "path": source_range["path"],
                "range": "8-10",
                "hash": source_range["content_hash"],
                "supported": supported,
                "contradicted": contradicted,
                "tool_run_id": tool_run_id,
                "evidence_id": evidence_id,
            },
        )
    finally:
        database = mongo.database()
        for collection, item_id in (
            (database.evidence, evidence_id),
            (database.tool_runs, tool_run_id),
            (database.model_calls, model_call_id),
            (database.proof_obligations, obligation_id),
        ):
            if item_id:
                await collection.delete_one({"id": item_id})
        if snapshot:
            await database.repository_files.delete_many({"snapshot_id": snapshot.id})
            await database.code_symbols.delete_many({"snapshot_id": snapshot.id})
            await database.repository_snapshots.delete_one({"id": snapshot.id})
        if project:
            await database.projects.delete_one({"id": project.id})
        await mongo.close()


@pytest.mark.integration
async def test_real_provider_structured_obligation_persists() -> None:
    settings = Settings()
    if not settings.mongo_is_configured or not settings.openrouter_api_key:
        pytest.skip("Atlas and OpenRouter must be configured")
    mongo = MongoManager(settings)
    await mongo.connect()
    plan_version_id = f"provider-smoke-{uuid4().hex}"
    try:
        repository = VerificationRepository(mongo)
        obligations = await ObligationExtractionService(
            ProviderGateway(settings, repository), repository
        ).extract(
            "provider-project",
            "provider-snapshot",
            plan_version_id,
            "Support partial refunds safely",
            "Change the refund ledger debit to use the requested refund amount.",
        )
        assert obligations and all(item.status == "PENDING" for item in obligations)
        call = await mongo.database().model_calls.find_one(sort=[("created_at", -1)])
        assert call and call["provider"] == "openrouter" and not call["used_fallback"]
        print(
            "PROVIDER_STRUCTURED",
            {
                "provider": call["provider"],
                "model": call["model"],
                "obligations": len(obligations),
                "fallback": call["used_fallback"],
            },
        )
    finally:
        await mongo.database().proof_obligations.delete_many({"plan_version_id": plan_version_id})
        if "call" in locals() and call:
            await mongo.database().model_calls.delete_one({"id": call["id"]})
        await mongo.close()
