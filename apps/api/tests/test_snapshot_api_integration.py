import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.mongo import MongoManager
from app.main import create_app
from app.services.models import ModelResult


@pytest.mark.integration
def test_snapshot_http_contract_uses_persisted_fixture_state(monkeypatch) -> None:
    settings = Settings()
    if not settings.mongo_is_configured:
        pytest.skip("MONGODB_URI is not configured")
    owner_id = f"api-itest-{uuid4().hex}"
    with TestClient(create_app(settings)) as client:
        invalid = client.post("/v1/projects", json={"name": "missing source"})
        assert invalid.status_code == 422
        malformed = client.post(
            "/v1/projects",
            json={
                "name": "bad public",
                "owner_id": owner_id,
                "repository_source": {
                    "type": "public_github",
                    "repository_url": "http://github.com/a/b",
                },
            },
        )
        assert malformed.status_code == 422
        project = client.post(
            "/v1/projects",
            json={
                "name": "fixture API",
                "owner_id": owner_id,
                "repository_source": {"type": "seeded_fixture", "fixture_id": "partial-refunds-v1"},
            },
        )
        assert project.status_code == 201
        project_id = project.json()["id"]
        snapshot = client.post(f"/v1/projects/{project_id}/snapshots")
        assert snapshot.status_code == 201
        body = snapshot.json()
        assert body["status"] == "READY"
        assert body["source_type"] == "seeded_fixture"
        assert body["resolved_commit_sha"] and body["root_content_hash"]
        assert body["files_indexed"] > 0 and body["symbols_indexed"] > 0
        assert "MONGODB_URI" not in str(body)
        assert "planproof-ingest-" not in str(body)
        repeated = client.post(f"/v1/projects/{project_id}/snapshots")
        assert repeated.status_code == 201
        assert repeated.json()["id"] == body["id"]
        fetched = client.get(f"/v1/snapshots/{body['id']}")
        assert fetched.status_code == 200 and fetched.json()["status"] == "READY"
        assert client.get("/v1/snapshots/not-a-real-snapshot").status_code == 404
        assert client.post("/v1/projects/not-a-real-project/snapshots").status_code == 404

        plan = client.post(
            f"/v1/projects/{project_id}/plan-versions",
            json={"change_request": "support refunds", "candidate_plan": "Use the refund amount."},
        )
        assert plan.status_code == 200 and plan.json()["version"] == 1
        plan_id = plan.json()["id"]
        amended = client.post(
            f"/v1/plan-versions/{plan_id}/amendments",
            json={"candidate_plan": "Use the refund amount and preserve audit history."},
        )
        assert amended.status_code == 200
        assert amended.json()["parent_plan_version_id"] == plan_id
        assert amended.json()["id"] != plan_id

        queued = []
        monkeypatch.setattr(
            "app.api.workflow.execute_verification_run.send", lambda run_id: queued.append(run_id)
        )
        run_response = client.post(
            "/v1/verification-runs",
            headers={"Idempotency-Key": f"api-run-{owner_id}"},
            json={"project_id": project_id, "snapshot_id": body["id"], "plan_version_id": plan_id},
        )
        assert run_response.status_code == 202 and run_response.json()["status"] == "QUEUED"
        run_id = run_response.json()["id"]
        duplicate = client.post(
            "/v1/verification-runs",
            headers={"Idempotency-Key": f"api-run-{owner_id}"},
            json={"project_id": project_id, "snapshot_id": body["id"], "plan_version_id": plan_id},
        )
        assert duplicate.json()["id"] == run_id and queued == [run_id]
        assert client.get(f"/v1/verification-runs/{run_id}").status_code == 200
        events = client.get(f"/v1/verification-runs/{run_id}/events")
        assert events.status_code == 200 and "run_created" in events.text

        async def model_complete(*_args, **_kwargs):
            return ModelResult(
                provider="mock",
                model="mock",
                latency_ms=1,
                retry_count=0,
                content='{"obligations":[{"statement":"Refund amount is used",'
                '"category":"BEHAVIOR","criticality":"HIGH","verification_hints":[]}]}',
            )

        monkeypatch.setattr("app.services.models.ProviderGateway.complete", model_complete)
        extracted = client.post(
            f"/v1/plan-versions/{plan_id}/extract-obligations",
            json={"snapshot_id": body["id"]},
        )
        assert extracted.status_code == 200
        obligation = extracted.json()[0]
        assert obligation["status"] == "PENDING" and obligation["evidence_ids"] == []
        assert client.get(f"/v1/proof-obligations/{obligation['id']}").status_code == 200
        assert client.get("/v1/proof-obligations/invented").status_code == 404
        tool = client.post(
            "/v1/tools/execute",
            json={
                "tool": "read_file_range",
                "input": {
                    "snapshot_id": body["id"],
                    "path": "db/models/refund.ts",
                    "start_line": 8,
                    "end_line": 10,
                },
            },
        )
        assert tool.status_code == 200 and tool.json()["path"] == "db/models/refund.ts"
        assert (
            client.post(
                "/v1/tools/execute",
                json={
                    "tool": "read_file_range",
                    "input": {
                        "snapshot_id": body["id"],
                        "path": "../secret",
                        "start_line": 1,
                        "end_line": 2,
                    },
                },
            ).status_code
            == 422
        )

    async def cleanup() -> None:
        mongo = MongoManager(settings)
        await mongo.connect()
        database = mongo.database()
        projects = [item["id"] async for item in database.projects.find({"owner_id": owner_id})]
        snapshots = [
            item["id"]
            async for item in database.repository_snapshots.find({"project_id": {"$in": projects}})
        ]
        await database.repository_files.delete_many({"snapshot_id": {"$in": snapshots}})
        await database.code_symbols.delete_many({"snapshot_id": {"$in": snapshots}})
        await database.repository_snapshots.delete_many({"project_id": {"$in": projects}})
        plan_ids = [
            item["id"]
            async for item in database.plan_versions.find({"project_id": {"$in": projects}})
        ]
        await database.proof_obligations.delete_many({"plan_version_id": {"$in": plan_ids}})
        run_ids = [
            item["id"]
            async for item in database.verification_runs.find({"project_id": {"$in": projects}})
        ]
        await database.events.delete_many({"run_id": {"$in": run_ids}})
        await database.verification_runs.delete_many({"id": {"$in": run_ids}})
        await database.plan_versions.delete_many({"project_id": {"$in": projects}})
        await database.projects.delete_many({"id": {"$in": projects}})
        await mongo.close()

    asyncio.run(cleanup())
