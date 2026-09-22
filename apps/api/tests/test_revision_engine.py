from __future__ import annotations

import pytest

from app.domain.facts import FactRelationship
from app.domain.investigation import InvestigationAction, InvestigationActionType
from app.domain.revised_plans import (
    ConfidenceBasis,
    PlanChangeType,
    RevisedPlanStatus,
)
from app.domain.runs import OriginalPlanStep, PlanVersion
from app.domain.verification import (
    Criticality,
    ObligationCategory,
    ObligationStatus,
    ProofObligation,
)
from app.services.investigation_planning import InvestigationPlanningService
from app.services.revision import (
    ModelPlanChange,
    ModelRevisedPlanResponse,
    ModelRevisedPlanStep,
    PlanRevisionService,
)
from app.workflow.engine import (
    _extract_explicit_imported_identifiers,
    _extract_explicit_paths,
    check_evidence_relevance,
    check_evidence_sufficiency,
)


def _make_obligation(
    id: str,
    statement: str,
    category: ObligationCategory = ObligationCategory.SYMBOL,
    status: ObligationStatus = ObligationStatus.PENDING,
    claim_type: str = "FILE_EXISTS",
    evidence_ids: list[str] | None = None,
    counter_evidence_ids: list[str] | None = None,
    source_plan_step_ids: list[str] | None = None,
) -> ProofObligation:
    return ProofObligation(
        id=id,
        project_id="proj-1",
        snapshot_id="snap-1",
        plan_version_id="pv-1",
        statement=statement,
        normalized_statement=statement.lower(),
        category=category,
        criticality=Criticality.HIGH,
        status=status,
        claim_type=claim_type,
        evidence_ids=evidence_ids or [],
        counter_evidence_ids=counter_evidence_ids or [],
        source_plan_step_ids=source_plan_step_ids or [],
    )


def test_extract_explicit_paths() -> None:
    ob = _make_obligation(
        "ob-1",
        "Update app/providers.tsx to include PrivyProvider and wrap components/auth-modal.tsx",
    )
    paths = _extract_explicit_paths(ob)
    assert "app/providers.tsx" in paths
    assert "components/auth-modal.tsx" in paths
    assert len(paths) == 2


def test_extract_explicit_imported_identifiers() -> None:
    ob = _make_obligation(
        "ob-1",
        "Verify that PrivyProvider is imported from '@privy-io/react-auth' in app/providers.tsx",
    )
    identifiers = _extract_explicit_imported_identifiers(ob)
    assert "PrivyProvider" in identifiers


def test_check_evidence_relevance_strict_path() -> None:
    ob = _make_obligation(
        "ob-1",
        "Verify PrivyProvider is imported in app/providers.tsx",
        claim_type="FILE_EXISTS",
    )

    # Exact path match
    is_rel = check_evidence_relevance(
        obligation=ob,
        path="app/providers.tsx",
        snippet="import { PrivyProvider } from '@privy-io/react-auth';",
        matched_query="PrivyProvider",
    )
    assert is_rel is True

    # Evidence from another file (e.g. app/dashboard/page.tsx) must NOT be relevant
    is_mismatch = check_evidence_relevance(
        obligation=ob,
        path="app/dashboard/page.tsx",
        snippet="import { PrivyProvider } from '@privy-io/react-auth';",
        matched_query="PrivyProvider",
    )
    assert is_mismatch is False


def test_check_evidence_sufficiency_symbol_and_env() -> None:
    ob = _make_obligation(
        "ob-1",
        "Verify PrivyProvider is imported in app/providers.tsx",
        claim_type="SYMBOL_EXPORTED",
    )

    # Symbol sufficiency: search for PrivyProvider, snippet has usePrivy only -> NOT sufficient
    is_suff = check_evidence_sufficiency(
        obligation=ob,
        path="app/providers.tsx",
        snippet="import { usePrivy } from '@privy-io/react-auth';",
        matched_query="usePrivy",
    )
    assert is_suff is False

    # Snippet has PrivyProvider imported -> sufficient
    is_suff_ok = check_evidence_sufficiency(
        obligation=ob,
        path="app/providers.tsx",
        snippet="import { PrivyProvider } from '@privy-io/react-auth';",
        matched_query="PrivyProvider",
    )
    assert is_suff_ok is True


class MockAsyncCursor:
    def __init__(self, docs: list[dict]) -> None:
        self.docs = docs

    def __aiter__(self):
        self._iter = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration from None


class MockCollection:
    def __init__(self, docs: list[dict] | None = None) -> None:
        self.docs = docs or []

    def find(self, query: dict, projection: dict | None = None) -> MockAsyncCursor:
        matched = []
        for d in self.docs:
            if "id" in query and "$in" in query["id"]:
                if d.get("id") in query["id"]["$in"]:
                    matched.append(d)
            elif "run_id" in query:
                if d.get("run_id") == query["run_id"]:
                    matched.append(d)
            elif "snapshot_id" in query:
                if d.get("snapshot_id") == query["snapshot_id"]:
                    matched.append(d)
            else:
                matched.append(d)
        return MockAsyncCursor(matched)

    async def insert_one(self, doc: dict) -> None:
        self.docs.append(doc)


class MockVerificationRepo:
    def __init__(self) -> None:
        class MockDB:
            evidence = MockCollection([
                {
                    "id": "ev-1",
                    "path": "app/providers.tsx",
                    "matched_query": "PrivyProvider",
                },
                {
                    "id": "ev-2",
                    "path": "app/dashboard/page.tsx",
                    "matched_query": "usePrivy",
                },
            ])
            human_questions = MockCollection([])
            authorized_facts = MockCollection([])
            repository_files = MockCollection([
                {"snapshot_id": "snap-1", "path": "app/providers.tsx"},
                {"snapshot_id": "snap-1", "path": "app/dashboard/page.tsx"},
                {"snapshot_id": "snap-1", "path": "package.json"},
            ])
            code_symbols = MockCollection([
                {"snapshot_id": "snap-1", "name": "PrivyProvider", "qualified_name": "PrivyProvider"},
                {"snapshot_id": "snap-1", "name": "usePrivy", "qualified_name": "usePrivy"},
            ])
            revised_plans = MockCollection([])

        self.database = MockDB()

        class MockMongo:
            def database(m_self):
                return self.database

        self._mongo = MockMongo()


class MockGateway:
    def __init__(self, response: ModelRevisedPlanResponse) -> None:
        self._response = response
        self.call_count = 0

    async def complete_structured(self, *args, **kwargs):
        self.call_count += 1
        return self._response


def test_investigation_planning_service_validation() -> None:
    service = InvestigationPlanningService(gateway=None, verification=MockVerificationRepo())  # type: ignore[arg-type]
    allowed_files = {"app/providers.tsx", "package.json"}

    valid_action = InvestigationAction(
        action_type=InvestigationActionType.INSPECT_EXACT_FILE,
        path="app/providers.tsx",
    )
    assert service.validate_action(valid_action, allowed_files) is not None

    invalid_path_action = InvestigationAction(
        action_type=InvestigationActionType.INSPECT_EXACT_FILE,
        path="evil/../../etc/passwd",
    )
    assert service.validate_action(invalid_path_action, allowed_files) is None

    non_existent_file_action = InvestigationAction(
        action_type=InvestigationActionType.INSPECT_EXACT_FILE,
        path="unknown/path.ts",
    )
    assert service.validate_action(non_existent_file_action, allowed_files) is None


def test_investigation_planning_service_fallback() -> None:
    service = InvestigationPlanningService(gateway=None, verification=MockVerificationRepo())  # type: ignore[arg-type]
    ob = _make_obligation(
        "ob-1",
        "Update app/providers.tsx to include PrivyProvider",
        claim_type="FILE_EXISTS",
    )
    intents = service.generate_deterministic_intents(
        obligations=[ob],
        snapshot_files={"app/providers.tsx", "package.json"},
    )
    assert len(intents) == 1
    intent = intents[0]
    assert intent.obligation_id == "ob-1"
    assert len(intent.proposed_actions) >= 1
    assert intent.proposed_actions[0].action_type == InvestigationActionType.INSPECT_EXACT_FILE
    assert intent.proposed_actions[0].path == "app/providers.tsx"


@pytest.mark.asyncio
async def test_plan_revision_fact_derivation_async() -> None:
    mock_repo = MockVerificationRepo()
    service = PlanRevisionService(gateway=None, verification=mock_repo)  # type: ignore[arg-type]

    ob_verified = _make_obligation(
        "ob-1",
        "app/providers.tsx exists",
        status=ObligationStatus.VERIFIED,
        evidence_ids=["ev-1"],
    )
    ob_disproved = _make_obligation(
        "ob-2",
        "LegacyAuthProvider exists",
        status=ObligationStatus.DISPROVED,
        counter_evidence_ids=["ev-2"],
    )

    facts = await service.derive_authorized_facts(
        run_id="run-1",
        snapshot_id="snap-1",
        obligations=[ob_verified, ob_disproved],
    )

    assert len(facts) == 2
    f1 = next(f for f in facts if f.obligation_id == "ob-1")
    assert f1.relationship == FactRelationship.SUPPORTS
    assert "app/providers.tsx" in f1.file_paths

    f2 = next(f for f in facts if f.obligation_id == "ob-2")
    assert f2.relationship == FactRelationship.CONTRADICTS
    assert "app/dashboard/page.tsx" in f2.file_paths


@pytest.mark.asyncio
async def test_plan_revision_synthesize_unavailable_when_no_model() -> None:
    mock_repo = MockVerificationRepo()
    service = PlanRevisionService(gateway=None, verification=mock_repo)  # type: ignore[arg-type]

    plan_ver = PlanVersion(
        id="pv-1",
        project_id="proj-1",
        version=1,
        change_request="Integrate Privy authentication",
        candidate_plan="1. Update app/providers.tsx with PrivyProvider",
        normalized_steps=[
            OriginalPlanStep(
                id="step-1", order=1, text="Update app/providers.tsx with PrivyProvider"
            )
        ],
    )

    ob_verified = _make_obligation(
        "ob-1",
        "app/providers.tsx exists",
        status=ObligationStatus.VERIFIED,
        evidence_ids=["ev-1"],
    )

    revised_plan = await service.synthesize(
        run_id="run-1",
        project_id="proj-1",
        snapshot_id="snap-1",
        plan_version=plan_ver,
        obligations=[ob_verified],
    )

    # When no model gateway is provided, status must safely become UNAVAILABLE without hallucination
    assert revised_plan.status == RevisedPlanStatus.UNAVAILABLE
    assert revised_plan.revision_version == 1
    assert "unavailable" in revised_plan.executive_summary.lower()


@pytest.mark.asyncio
async def test_revision_rejects_file_path_as_existing_symbol() -> None:
    mock_repo = MockVerificationRepo()
    # Candidate response where model hallucinated file path in existing_target_symbols
    model_response = ModelRevisedPlanResponse(
        executive_summary="Migrating auth provider.",
        plan_changes=[
            ModelPlanChange(
                change_type="MODIFY",
                source_plan_step_ids=["step-1"],
                original_text="Update providers",
                updated_text="Update app/providers.tsx",
                rationale="Verified present-state fact.",
                basis_fact_ids=[],  # will be filled
            )
        ],
        implementation_plan=[
            ModelRevisedPlanStep(
                order=1,
                action="Update app/providers.tsx",
                rationale="Grounding update",
                status="MODIFY",
                source_plan_step_ids=["step-1"],
                existing_target_files=["app/providers.tsx"],
                existing_target_symbols=["app/providers.tsx", "PrivyProvider"],  # PATH present!
                proposed_new_symbols=["CustomAuthProvider"],
            )
        ],
    )

    gateway = MockGateway(model_response)
    service = PlanRevisionService(gateway=gateway, verification=mock_repo)  # type: ignore[arg-type]

    ob = _make_obligation(
        "ob-1",
        "app/providers.tsx imports PrivyProvider",
        status=ObligationStatus.VERIFIED,
        evidence_ids=["ev-1"],
    )

    facts = await service.derive_authorized_facts("run-1", "snap-1", [ob])
    model_response.plan_changes[0].basis_fact_ids = [facts[0].id]
    model_response.implementation_plan[0].basis_fact_ids = [facts[0].id]

    plan_ver = PlanVersion(
        id="pv-1",
        project_id="proj-1",
        version=1,
        change_request="Migrate auth",
        candidate_plan="1. Update providers",
    )

    revised_plan = await service.synthesize(
        run_id="run-1",
        project_id="proj-1",
        snapshot_id="snap-1",
        plan_version=plan_ver,
        obligations=[ob],
    )

    step = revised_plan.implementation_plan[0]
    # Path MUST be removed from existing_target_symbols
    assert "app/providers.tsx" not in step.existing_target_symbols
    assert "PrivyProvider" in step.existing_target_symbols
    assert "CustomAuthProvider" in step.proposed_new_symbols


@pytest.mark.asyncio
async def test_revision_existing_symbol_must_be_snapshot_grounded() -> None:
    mock_repo = MockVerificationRepo()
    # Model claims CustomAuthProvider is an EXISTING symbol, but snapshot only has PrivyProvider
    model_response = ModelRevisedPlanResponse(
        executive_summary="Migrating auth provider.",
        plan_changes=[
            ModelPlanChange(
                change_type="MODIFY",
                source_plan_step_ids=["step-1"],
                original_text="Update providers",
                updated_text="Update app/providers.tsx",
                rationale="Verified present-state fact.",
                basis_fact_ids=[],
            )
        ],
        implementation_plan=[
            ModelRevisedPlanStep(
                order=1,
                action="Update app/providers.tsx",
                rationale="Grounding update",
                status="MODIFY",
                source_plan_step_ids=["step-1"],
                existing_target_files=["app/providers.tsx"],
                existing_target_symbols=["CustomAuthProvider", "PrivyProvider"],  # CustomAuthProvider not in snapshot
                proposed_new_symbols=[],
            )
        ],
    )

    gateway = MockGateway(model_response)
    service = PlanRevisionService(gateway=gateway, verification=mock_repo)  # type: ignore[arg-type]

    ob = _make_obligation(
        "ob-1",
        "app/providers.tsx imports PrivyProvider",
        status=ObligationStatus.VERIFIED,
        evidence_ids=["ev-1"],
    )

    facts = await service.derive_authorized_facts("run-1", "snap-1", [ob])
    model_response.plan_changes[0].basis_fact_ids = [facts[0].id]
    model_response.implementation_plan[0].basis_fact_ids = [facts[0].id]

    plan_ver = PlanVersion(
        id="pv-1",
        project_id="proj-1",
        version=1,
        change_request="Migrate auth",
        candidate_plan="1. Update providers",
    )

    revised_plan = await service.synthesize(
        run_id="run-1",
        project_id="proj-1",
        snapshot_id="snap-1",
        plan_version=plan_ver,
        obligations=[ob],
    )

    step = revised_plan.implementation_plan[0]
    # CustomAuthProvider MUST NOT be in existing_target_symbols; moved to proposed_new_symbols
    assert "CustomAuthProvider" not in step.existing_target_symbols
    assert "CustomAuthProvider" in step.proposed_new_symbols
    assert "PrivyProvider" in step.existing_target_symbols


@pytest.mark.asyncio
async def test_inconclusive_path_cannot_claim_file_does_not_exist() -> None:
    mock_repo = MockVerificationRepo()
    # Model attempts to say "components/auth-modal.tsx does not exist" without a contradiction fact
    model_response = ModelRevisedPlanResponse(
        executive_summary="Migrating auth provider.",
        plan_changes=[
            ModelPlanChange(
                change_type="REMOVE",
                source_plan_step_ids=["step-4"],
                original_text="Update components/auth-modal.tsx",
                updated_text=None,
                rationale="The file components/auth-modal.tsx does not exist in the repository snapshot per authorized facts",
                basis_fact_ids=[],
            )
        ],
        implementation_plan=[
            ModelRevisedPlanStep(
                order=1,
                action="Remove components/auth-modal.tsx step because it does not exist",
                rationale="components/auth-modal.tsx does not exist in the repository snapshot",
                status="REMOVE",
                source_plan_step_ids=["step-4"],
                basis_fact_ids=[],
            )
        ],
    )

    gateway = MockGateway(model_response)
    service = PlanRevisionService(gateway=gateway, verification=mock_repo)  # type: ignore[arg-type]

    ob_inconclusive = _make_obligation(
        "ob-4",
        "components/auth-modal.tsx triggers login",
        status=ObligationStatus.INCONCLUSIVE,
    )

    plan_ver = PlanVersion(
        id="pv-1",
        project_id="proj-1",
        version=1,
        change_request="Migrate auth",
        candidate_plan="4. Update components/auth-modal.tsx",
    )

    revised_plan = await service.synthesize(
        run_id="run-1",
        project_id="proj-1",
        snapshot_id="snap-1",
        plan_version=plan_ver,
        obligations=[ob_inconclusive],
    )

    change = revised_plan.plan_changes[0]
    assert change.change_type == PlanChangeType.UNRESOLVED
    assert "does not exist" not in change.rationale
    assert "not established" in change.rationale.lower()

    step = revised_plan.implementation_plan[0]
    assert step.status == PlanChangeType.UNRESOLVED
    assert step.confidence_basis == ConfidenceBasis.UNRESOLVED
    assert "does not exist" not in step.rationale
    assert "does not exist" not in step.action


def test_classify_obligation_routing() -> None:
    from app.domain.verification import SemanticRole
    from app.workflow.engine import classify_obligation_routing

    # 1. PROPOSED_ACTION -> PROPOSED_ACTION (preserved for synthesis only)
    ob_prop = _make_obligation("ob-p", "Replace PrivyProvider with CustomAuthProvider in app/providers.tsx")
    ob_prop.semantic_role = SemanticRole.PROPOSED_ACTION
    assert classify_obligation_routing(ob_prop) == "PROPOSED_ACTION"

    # 2. HUMAN_DECISION -> HUMAN_AUTHORITY
    ob_hum = _make_obligation("ob-h", "Choose 30-day retention period for customer conversations")
    ob_hum.semantic_role = SemanticRole.HUMAN_DECISION
    assert classify_obligation_routing(ob_hum) == "HUMAN_AUTHORITY"

    # 3. CURRENT_STATE_ASSUMPTION -> REPO_INVESTIGATION
    ob_curr = _make_obligation("ob-c", "app/providers.tsx imports PrivyProvider")
    ob_curr.semantic_role = SemanticRole.CURRENT_STATE_ASSUMPTION
    assert classify_obligation_routing(ob_curr) == "REPO_INVESTIGATION"

    # 4. EXISTING_DEPENDENCY -> REPO_INVESTIGATION
    ob_dep = _make_obligation("ob-d", "CustomAuthProvider exists in the repository")
    ob_dep.semantic_role = SemanticRole.EXISTING_DEPENDENCY
    assert classify_obligation_routing(ob_dep) == "REPO_INVESTIGATION"

    # 5. Technical CONSTRAINT -> REPO_INVESTIGATION
    ob_tech_c = _make_obligation("ob-tc", "Column user_id in schema users.sql is unique")
    ob_tech_c.semantic_role = SemanticRole.CONSTRAINT
    assert classify_obligation_routing(ob_tech_c) == "REPO_INVESTIGATION"

    # 6. Business CONSTRAINT -> HUMAN_AUTHORITY
    ob_biz_c = _make_obligation("ob-bc", "Data retention policy requires user approval before deletion")
    ob_biz_c.semantic_role = SemanticRole.CONSTRAINT
    assert classify_obligation_routing(ob_biz_c) == "HUMAN_AUTHORITY"
