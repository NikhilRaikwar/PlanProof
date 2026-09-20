import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.mongo import MongoManager
from app.main import create_app


@pytest.mark.integration
def test_snapshot_http_contract_uses_persisted_fixture_state() -> None:
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
                "name": "bad public", "owner_id": owner_id,
                "repository_source": {"type": "public_github", "repository_url": "http://github.com/a/b"},
            },
        )
        assert malformed.status_code == 422
        project = client.post(
            "/v1/projects",
            json={
                "name": "fixture API", "owner_id": owner_id,
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
        await database.projects.delete_many({"id": {"$in": projects}})
        await mongo.close()

    asyncio.run(cleanup())
