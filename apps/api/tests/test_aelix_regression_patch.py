from __future__ import annotations

import copy
import re

import pytest

from app.domain.runs import (
    PlanVersion,
    RepositorySnapshot,
    SnapshotStatus,
    VerificationRun,
    VerificationRunStatus,
)
from app.domain.verification import (
    Criticality,
    EvidenceType,
    ObligationCategory,
    ObligationStatus,
    ProofObligation,
    SemanticRole,
    TargetIntent,
)
from app.services.obligations import (
    _extract_canonical_paths_from_text,
    classify_target_intent,
)
from app.workflow.engine import (
    _extract_explicit_paths,
    _extract_primary_obligation_symbols,
    check_evidence_sufficiency,
    extract_obligation_queries,
)


class AsyncCursor:
    def __init__(self, items: list[dict]):
        self.items = items
        self._idx = 0

    def sort(self, *args, **kwargs):
        return self

    def limit(self, n: int):
        self.items = self.items[:n]
        return self

    def __aiter__(self):
        self._idx = 0
        return self

    async def __anext__(self):
        if self._idx < len(self.items):
            item = self.items[self._idx]
            self._idx += 1
            return item
        raise StopAsyncIteration

    async def to_list(self, length: int | None = None):
        return self.items[:length] if length is not None else self.items


class InMemoryCollection:
    def __init__(self):
        self.docs: list[dict] = []

    async def insert_one(self, doc: dict):
        d = copy.deepcopy(doc)
        if "id" not in d and "_id" in d:
            d["id"] = d["_id"]
        elif "id" in d and "_id" not in d:
            d["_id"] = d["id"]
        self.docs.append(d)
        return type("Result", (), {"inserted_id": d.get("_id")})()

    async def find_one(self, query: dict, sort=None):
        res = await self._filter(query)
        return copy.deepcopy(res[0]) if res else None

    def find(self, query: dict, projection=None):
        res = self._filter_sync(query)
        return AsyncCursor([copy.deepcopy(r) for r in res])

    async def count_documents(self, query: dict) -> int:
        return len(await self._filter(query))

    async def update_one(self, query: dict, update: dict, upsert: bool = False):
        matches = await self._filter(query)
        if matches:
            target = matches[0]
            if "$set" in update:
                target.update(update["$set"])
            return type("Result", (), {"modified_count": 1, "matched_count": 1})()
        elif upsert:
            new_doc = copy.deepcopy(query)
            if "$setOnInsert" in update:
                new_doc.update(update["$setOnInsert"])
            if "$set" in update:
                new_doc.update(update["$set"])
            await self.insert_one(new_doc)
            return type("Result", (), {"modified_count": 0, "matched_count": 0, "upserted_id": new_doc.get("id")})()
        return type("Result", (), {"modified_count": 0, "matched_count": 0})()

    async def _filter(self, query: dict) -> list[dict]:
        return self._filter_sync(query)

    def _filter_sync(self, query: dict) -> list[dict]:
        results = []
        for d in self.docs:
            match = True
            for k, v in query.items():
                if k == "$or":
                    or_match = False
                    for sub_q in v:
                        if all(d.get(sk) == sv for sk, sv in sub_q.items()):
                            or_match = True
                            break
                    if not or_match:
                        match = False
                        break
                elif isinstance(v, dict):
                    if "$in" in v:
                        if d.get(k) not in v["$in"]:
                            match = False
                            break
                    elif "$regex" in v:
                        pattern = v["$regex"]
                        val = str(d.get(k, ""))
                        if not re.search(pattern, val, re.IGNORECASE):
                            match = False
                            break
                elif d.get(k) != v:
                    match = False
                    break
            if match:
                results.append(d)
        return results


class InMemoryDatabase:
    def __init__(self):
        self.repository_files = InMemoryCollection()
        self.snapshots = InMemoryCollection()
        self.repository_snapshots = InMemoryCollection()
        self.verification_runs = InMemoryCollection()
        self.proof_obligations = InMemoryCollection()
        self.evidence = InMemoryCollection()
        self.tool_runs = InMemoryCollection()
        self.code_symbols = InMemoryCollection()
        self.plan_versions = InMemoryCollection()
        self.events = InMemoryCollection()
        self.human_questions = InMemoryCollection()
        self.revised_plans = InMemoryCollection()
        self.projects = InMemoryCollection()
        self.model_calls = InMemoryCollection()

    def database(self):
        return self


def test_classify_target_intent_generic():
    assert classify_target_intent("Update src/foo.ts to use new auth") == TargetIntent.MUST_EXIST
    assert classify_target_intent("Modify cmd/server.go handler") == TargetIntent.MUST_EXIST
    assert classify_target_intent("Replace AuthProvider with CustomProvider in app/main.py") == TargetIntent.MUST_EXIST
    assert classify_target_intent("Delete lib/deprecated.rb") == TargetIntent.MUST_EXIST
    assert classify_target_intent("Create src/new_module.ts") == TargetIntent.CREATE_NEW
    assert classify_target_intent("Add a new endpoint in routes.py") == TargetIntent.CREATE_NEW
    assert classify_target_intent("Create or update src/config.json") == TargetIntent.CREATE_OR_UPDATE
    assert classify_target_intent("Create and then update src/config.json") == TargetIntent.CREATE_OR_UPDATE
    assert classify_target_intent("Do not update src/legacy.ts") == TargetIntent.UNKNOWN


def test_exact_path_never_becomes_lexical_query():
    ob = ProofObligation(
        project_id="proj-1",
        snapshot_id="snap-1",
        plan_version_id="pv-1",
        statement="src/config.ts reads API_URL from import.meta.env",
        normalized_statement="src/config.ts reads api_url from import.meta.env",
        semantic_role=SemanticRole.CURRENT_STATE_ASSUMPTION,
        category=ObligationCategory.DEPENDENCY,
        criticality=Criticality.HIGH,
        verification_hints=["src/config.ts", "API_URL"],
    )

    explicit_paths = _extract_explicit_paths(ob)
    assert explicit_paths == ["src/config.ts"]

    symbols = _extract_primary_obligation_symbols(ob)
    assert "src/config.ts" not in symbols
    assert "API_URL" in symbols

    queries = extract_obligation_queries(ob)
    query_strings = [q[0] for q in queries]
    assert "src/config.ts" not in query_strings
    assert "API_URL" in query_strings


def test_claim_sufficiency_generic_env_identifiers():
    ob = ProofObligation(
        project_id="proj-1",
        snapshot_id="snap-1",
        plan_version_id="pv-1",
        statement="src/App.tsx reads VITE_PRIVY_APP_ID from import.meta.env.",
        normalized_statement="src/app.tsx reads vite_privy_app_id from import.meta.env.",
        semantic_role=SemanticRole.CURRENT_STATE_ASSUMPTION,
        category=ObligationCategory.DEPENDENCY,
        criticality=Criticality.HIGH,
        verification_hints=["src/App.tsx", "VITE_PRIVY_APP_ID"],
    )

    valid_snippet = """
    const App = () => {
      const privyAppId = import.meta.env.VITE_PRIVY_APP_ID;
      return <div />
    }
    """
    assert check_evidence_sufficiency(ob, "src/App.tsx", valid_snippet, "src/App.tsx") is True

    # Missing exact env variable identifier
    invalid_snippet = """
    const App = () => {
      const otherKey = import.meta.env.OTHER_KEY;
      return <div />
    }
    """
    assert check_evidence_sufficiency(ob, "src/App.tsx", invalid_snippet, "src/App.tsx") is False

    # Different path
    assert check_evidence_sufficiency(ob, "src/Other.tsx", valid_snippet, "src/Other.tsx") is False


def test_derived_prerequisites_for_must_exist():
    # Update action derives prerequisite
    paths = _extract_canonical_paths_from_text("Update src/auth/AuthProvider.tsx to expose useAuth")
    assert paths == ["src/auth/AuthProvider.tsx"]

    intent = classify_target_intent("Update src/auth/AuthProvider.tsx to expose useAuth")
    assert intent == TargetIntent.MUST_EXIST

    # Create action does NOT derive prerequisite
    create_intent = classify_target_intent("Create src/auth/AuthProvider.tsx to expose useAuth")
    assert create_intent == TargetIntent.CREATE_NEW


@pytest.mark.asyncio
async def test_evidence_reuse_and_manifest_absence():
    from app.core.config import Settings
    from app.domain.common import new_id
    from app.repositories.runs import RunRepository
    from app.repositories.verification import VerificationRepository
    from app.workflow.engine import VerificationWorkflow

    test_db = InMemoryDatabase()

    run_repo = RunRepository(test_db)
    ver_repo = VerificationRepository(test_db)
    settings = Settings(verification_max_tool_calls=10)

    project_id = f"proj-{new_id()[:8]}"
    snapshot_id = f"snap-{new_id()[:8]}"
    plan_version_id = f"pv-{new_id()[:8]}"
    run_id = f"run-{new_id()[:8]}"

    # Setup plan version
    plan_ver = PlanVersion(
        id=plan_version_id,
        project_id=project_id,
        version=1,
        change_request="Migrate auth",
        candidate_plan="Update auth",
    )
    await run_repo.create_plan_version(plan_ver)

    # Setup ready snapshot
    snapshot = RepositorySnapshot(
        id=snapshot_id,
        project_id=project_id,
        repository_identity="test/aelix",
        parser_version="1.0.0",
        index_version="1.0.0",
        status=SnapshotStatus.READY,
        files_indexed=2,
        root_content_hash="roothash123",
    )
    await run_repo.create_snapshot(snapshot)

    # Insert repository files
    app_text = (
        "import React from 'react';\n"
        "import { PrivyProvider } from '@privy-io/react-auth';\n"
        "const App = () => {\n"
        "  const privyAppId = import.meta.env.VITE_PRIVY_APP_ID;\n"
        "  return <PrivyProvider appId={privyAppId} />;\n"
        "};\n"
    )
    import hashlib
    app_hash = hashlib.sha256(app_text.encode()).hexdigest()
    await test_db.repository_files.insert_one({
        "snapshot_id": snapshot_id,
        "path": "src/App.tsx",
        "text": app_text,
        "content_hash": app_hash,
        "language": "typescript",
    })

    # Obligation 1: imports PrivyProvider
    ob1 = ProofObligation(
        id=f"ob-{new_id()[:8]}",
        project_id=project_id,
        snapshot_id=snapshot_id,
        plan_version_id=plan_version_id,
        run_id=run_id,
        statement="src/App.tsx imports PrivyProvider from '@privy-io/react-auth'.",
        normalized_statement="src/app.tsx imports privyprovider from '@privy-io/react-auth'.",
        semantic_role=SemanticRole.CURRENT_STATE_ASSUMPTION,
        category=ObligationCategory.DEPENDENCY,
        criticality=Criticality.HIGH,
        verification_hints=["src/App.tsx", "PrivyProvider"],
    )
    await ver_repo.create_obligation(ob1)

    # Obligation 2: reads VITE_PRIVY_APP_ID from import.meta.env
    ob2 = ProofObligation(
        id=f"ob-{new_id()[:8]}",
        project_id=project_id,
        snapshot_id=snapshot_id,
        plan_version_id=plan_version_id,
        run_id=run_id,
        statement="src/App.tsx reads VITE_PRIVY_APP_ID from import.meta.env.",
        normalized_statement="src/app.tsx reads vite_privy_app_id from import.meta.env.",
        semantic_role=SemanticRole.CURRENT_STATE_ASSUMPTION,
        category=ObligationCategory.DEPENDENCY,
        criticality=Criticality.HIGH,
        verification_hints=["src/App.tsx", "VITE_PRIVY_APP_ID"],
    )
    await ver_repo.create_obligation(ob2)

    # Obligation 3: src/auth/AuthProvider.tsx exists in the current snapshot (MUST_EXIST prerequisite)
    ob3 = ProofObligation(
        id=f"ob-{new_id()[:8]}",
        project_id=project_id,
        snapshot_id=snapshot_id,
        plan_version_id=plan_version_id,
        run_id=run_id,
        statement="src/auth/AuthProvider.tsx exists in the current snapshot.",
        normalized_statement="src/auth/authprovider.tsx exists in the current snapshot.",
        semantic_role=SemanticRole.EXISTING_DEPENDENCY,
        category=ObligationCategory.DEPENDENCY,
        criticality=Criticality.HIGH,
        verification_hints=["src/auth/AuthProvider.tsx"],
    )
    await ver_repo.create_obligation(ob3)

    # Create Run
    run = VerificationRun(
        id=run_id,
        project_id=project_id,
        snapshot_id=snapshot_id,
        plan_version_id=plan_version_id,
        status=VerificationRunStatus.VERIFYING,
    )
    await run_repo.create_run(run)

    workflow = VerificationWorkflow(run_repo, ver_repo, settings)
    await workflow.run(run_id)

    # Verify outcomes
    updated_ob1 = await ver_repo.get_obligation(ob1.id)
    updated_ob2 = await ver_repo.get_obligation(ob2.id)
    updated_ob3 = await ver_repo.get_obligation(ob3.id)
    updated_run = await run_repo.get_run(run_id)

    assert updated_ob1.status == ObligationStatus.VERIFIED
    assert len(updated_ob1.evidence_ids) >= 1

    # Obligation 2 MUST be VERIFIED via evidence reuse
    assert updated_ob2.status == ObligationStatus.VERIFIED
    assert len(updated_ob2.evidence_ids) >= 1

    # Obligation 3 MUST be DISPROVED because path is absent from complete snapshot manifest
    assert updated_ob3.status == ObligationStatus.DISPROVED
    assert len(updated_ob3.counter_evidence_ids) >= 1

    counter_ev = await ver_repo.get_evidence(updated_ob3.counter_evidence_ids[0])
    assert counter_ev.evidence_type == EvidenceType.SNAPSHOT_PATH_MEMBERSHIP
    assert counter_ev.relationship == "CONTRADICTS"
    assert counter_ev.path == "src/auth/AuthProvider.tsx"

    # Deterministic Gate MUST be BLOCKED because a prerequisite was disproved
    assert updated_run.status == VerificationRunStatus.BLOCKED
