from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.domain.facts import AuthorizedFact, FactRelationship
from app.domain.revised_plans import (
    ConfidenceBasis,
    PlanChange,
    PlanChangeType,
    RevisedPlan,
    RevisedPlanStatus,
    RevisedPlanStep,
)
from app.domain.runs import PlanVersion
from app.domain.verification import ObligationStatus, ProofObligation
from app.repositories.revised_plans import RevisedPlansRepository

if TYPE_CHECKING:
    from app.repositories.verification import VerificationRepository
    from app.services.models import ProviderGateway

logger = logging.getLogger(__name__)

_PATH_EXTENSIONS = (
    ".tsx",
    ".ts",
    ".jsx",
    ".js",
    ".py",
    ".json",
    ".md",
    ".yaml",
    ".yml",
    ".html",
    ".css",
    ".scss",
    ".sql",
    ".go",
    ".rs",
    ".java",
    ".c",
    ".cpp",
)


def _is_path_like(s: str | None) -> bool:
    """Returns True if the string looks like a file path rather than a code symbol."""
    if not s or not isinstance(s, str):
        return False
    clean = s.strip()
    if "/" in clean or "\\" in clean:
        return True
    return any(clean.lower().endswith(ext) for ext in _PATH_EXTENSIONS)


class ModelPlanChange(BaseModel):
    change_type: str
    source_plan_step_ids: list[str] = Field(default_factory=list)
    original_text: str | None = None
    updated_text: str | None = None
    rationale: str = ""
    basis_fact_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    human_decision_ids: list[str] = Field(default_factory=list)


class ModelRevisedPlanStep(BaseModel):
    order: int
    action: str
    rationale: str
    status: str = "MODIFY"
    source_plan_step_ids: list[str] = Field(default_factory=list)
    basis_fact_ids: list[str] = Field(default_factory=list)
    supporting_obligation_ids: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    supporting_human_decision_ids: list[str] = Field(default_factory=list)
    unresolved_dependency_ids: list[str] = Field(default_factory=list)
    existing_target_files: list[str] = Field(default_factory=list)
    proposed_new_files: list[str] = Field(default_factory=list)
    existing_target_symbols: list[str] = Field(default_factory=list)
    proposed_new_symbols: list[str] = Field(default_factory=list)
    target_symbols: list[str] = Field(default_factory=list)
    confidence_basis: str = "UNRESOLVED"


class ModelRevisedPlanResponse(BaseModel):
    executive_summary: str
    plan_changes: list[ModelPlanChange] = Field(default_factory=list)
    implementation_plan: list[ModelRevisedPlanStep] = Field(default_factory=list)


class PlanRevisionService:
    def __init__(
        self,
        gateway: ProviderGateway | None,
        verification: VerificationRepository,
    ) -> None:
        self.gateway = gateway
        self.verification = verification
        self.database = verification.database
        self.repository = RevisedPlansRepository(verification.database)

    async def derive_authorized_facts(
        self,
        run_id: str,
        snapshot_id: str,
        obligations: list[ProofObligation],
    ) -> list[AuthorizedFact]:
        """Derive canonical server-owned facts strictly from VERIFIED, DISPROVED, or answered human obligations."""
        facts: list[AuthorizedFact] = []

        for ob in obligations:
            if ob.status == ObligationStatus.VERIFIED and ob.evidence_ids:
                cursor = self.database.evidence.find({"id": {"$in": ob.evidence_ids}})
                ev_docs = [doc async for doc in cursor]
                paths = list({doc["path"] for doc in ev_docs if doc.get("path")})
                symbols = list(
                    {
                        doc["matched_query"]
                        for doc in ev_docs
                        if doc.get("matched_query") and not _is_path_like(doc["matched_query"])
                    }
                )
                facts.append(
                    AuthorizedFact(
                        run_id=run_id,
                        snapshot_id=snapshot_id,
                        obligation_id=ob.id,
                        obligation_status=ob.status,
                        semantic_role=getattr(ob, "semantic_role", None),
                        canonical_fact=f"Present-state repository fact: {ob.statement}",
                        relationship=FactRelationship.SUPPORTS,
                        evidence_ids=ob.evidence_ids,
                        file_paths=paths,
                        symbols=symbols,
                    )
                )
            elif ob.status == ObligationStatus.DISPROVED and ob.counter_evidence_ids:
                cursor = self.database.evidence.find({"id": {"$in": ob.counter_evidence_ids}})
                ev_docs = [doc async for doc in cursor]
                paths = list({doc["path"] for doc in ev_docs if doc.get("path")})
                symbols = list(
                    {
                        doc["matched_query"]
                        for doc in ev_docs
                        if doc.get("matched_query") and not _is_path_like(doc["matched_query"])
                    }
                )
                facts.append(
                    AuthorizedFact(
                        run_id=run_id,
                        snapshot_id=snapshot_id,
                        obligation_id=ob.id,
                        obligation_status=ob.status,
                        semantic_role=getattr(ob, "semantic_role", None),
                        canonical_fact=f"Contradicted candidate assumption: {ob.statement}",
                        relationship=FactRelationship.CONTRADICTS,
                        evidence_ids=ob.counter_evidence_ids,
                        file_paths=paths,
                        symbols=symbols,
                    )
                )

        # Check for answered human decisions
        cursor = self.database.human_questions.find(
            {"run_id": run_id, "answer": {"$exists": True, "$ne": None}}
        )
        async for q_doc in cursor:
            facts.append(
                AuthorizedFact(
                    run_id=run_id,
                    snapshot_id=snapshot_id,
                    obligation_id=q_doc["obligation_id"],
                    obligation_status=ObligationStatus.VERIFIED,
                    canonical_fact=f"Human authority decision: {q_doc.get('answer')}",
                    relationship=FactRelationship.HUMAN_CONFIRMED,
                    human_decision_id=q_doc["id"],
                )
            )

        # Persist facts for auditability
        for f in facts:
            try:
                await self.database.authorized_facts.insert_one(f.model_dump(mode="python"))
            except Exception:
                pass

        return facts

    async def synthesize(
        self,
        run_id: str,
        project_id: str,
        snapshot_id: str,
        plan_version: PlanVersion,
        obligations: list[ProofObligation],
        status_override: RevisedPlanStatus | None = None,
        revision_version: int = 1,
    ) -> RevisedPlan:
        """Synthesize an evidence-grounded updated implementation plan with strict server-side validation."""
        # 1. Derive authoritative facts
        facts = await self.derive_authorized_facts(run_id, snapshot_id, obligations)
        fact_map = {f.id: f for f in facts}
        valid_fact_evidence_ids = {ev_id for f in facts for ev_id in f.evidence_ids}
        valid_human_ids = {
            f.human_decision_id for f in facts if getattr(f, "human_decision_id", None)
        }

        # 2. Fetch snapshot file list for target file validation
        cursor = self.database.repository_files.find({"snapshot_id": snapshot_id}, {"path": 1})
        snapshot_files = {doc["path"] async for doc in cursor}

        # 3. Collect all snapshot-grounded symbols
        snapshot_symbols: set[str] = set()
        try:
            cursor_sym = self.database.code_symbols.find({"snapshot_id": snapshot_id})
            async for sym_doc in cursor_sym:
                for key in ("name", "qualified_name"):
                    val = sym_doc.get(key)
                    if val and isinstance(val, str) and not _is_path_like(val):
                        snapshot_symbols.add(val)
                        for token in re.findall(r"[A-Za-z_$][\w$]*", val):
                            snapshot_symbols.add(token)
        except Exception as exc:
            logger.warning(
                f"Failed to fetch snapshot code symbols for snapshot_id={snapshot_id}: {exc}. Failing closed to authorized facts."
            )

        for f in facts:
            for sym in f.symbols:
                if sym and not _is_path_like(sym):
                    snapshot_symbols.add(sym)
                    for token in re.findall(r"[A-Za-z_$][\w$]*", sym):
                        snapshot_symbols.add(token)

        # 4. Determine plan status
        statuses = {ob.status for ob in obligations}
        if status_override:
            final_status = status_override
        elif ObligationStatus.HUMAN_REQUIRED in statuses:
            final_status = RevisedPlanStatus.AWAITING_HUMAN_DECISION
        elif ObligationStatus.DISPROVED in statuses or ObligationStatus.INCONCLUSIVE in statuses:
            final_status = RevisedPlanStatus.PROVISIONAL
        elif statuses <= {ObligationStatus.VERIFIED}:
            final_status = RevisedPlanStatus.EVIDENCE_GROUNDED
        else:
            final_status = RevisedPlanStatus.PROVISIONAL

        # Collect allowed context to enforce output fidelity boundary
        allowed_corpus_parts = [
            plan_version.change_request,
            plan_version.candidate_plan,
        ]
        for s in plan_version.normalized_steps:
            allowed_corpus_parts.append(s.text)
        for f in facts:
            allowed_corpus_parts.append(f.canonical_fact)
            allowed_corpus_parts.extend(f.file_paths)
            allowed_corpus_parts.extend(f.symbols)
        if valid_fact_evidence_ids:
            cursor_ev = self.database.evidence.find({"id": {"$in": list(valid_fact_evidence_ids)}})
            async for ev_doc in cursor_ev:
                if ev_doc.get("snippet"):
                    allowed_corpus_parts.append(ev_doc["snippet"])
                if ev_doc.get("summary"):
                    allowed_corpus_parts.append(ev_doc["summary"])
        allowed_grounding_corpus = " ".join(allowed_corpus_parts).lower()

        def _check_output_fidelity(text: str) -> list[str]:
            violations = []
            env_matches = re.findall(
                r"\b(?:VITE_|REACT_APP_|NEXT_PUBLIC_|[A-Z0-9_]{3,}_(?:NAME|KEY|SECRET|TOKEN|URL|APP|ID|AUTH|API|ENV))\b",
                text,
            )
            for env in env_matches:
                if env.lower() not in allowed_grounding_corpus:
                    violations.append(f"ungrounded environment variable '{env}'")

            concrete_techs = [
                "jwt",
                "json web token",
                "oauth",
                "auth0",
                "clerk",
                "firebase",
                "supabase",
                "cognito",
                "nextauth",
                "passport",
                "lucia",
                "zustand",
                "redux",
                "mobx",
                "recoil",
                "graphql",
                "grpc",
                "prisma",
                "drizzle",
            ]
            for tech in concrete_techs:
                if re.search(rf"\b{re.escape(tech)}\b", text, re.IGNORECASE):
                    if tech.lower() not in allowed_grounding_corpus:
                        violations.append(f"unrequested concrete technology '{tech.upper()}'")
            return violations

        # 5. Invoke model synthesis if gateway is available
        model_call_id: str | None = None
        plan_changes: list[PlanChange] = []
        implementation_plan: list[RevisedPlanStep] = []
        executive_summary = ""

        if self.gateway:
            prompt_payload = {
                "change_request": plan_version.change_request,
                "original_plan_steps": [
                    {"id": s.id, "order": s.order, "text": s.text}
                    for s in plan_version.normalized_steps
                ],
                "authorized_facts": [
                    {
                        "fact_id": f.id,
                        "obligation_id": f.obligation_id,
                        "canonical_fact": f.canonical_fact,
                        "relationship": str(f.relationship),
                        "file_paths": f.file_paths,
                        "symbols": f.symbols,
                        "evidence_ids": f.evidence_ids,
                    }
                    for f in facts
                ],
                "unresolved_items": [
                    {
                        "obligation_id": ob.id,
                        "statement": ob.statement,
                        "status": str(ob.status),
                        "reason": ob.proposal_metadata.get("inconclusive_reason", ""),
                    }
                    for ob in obligations
                    if ob.status in {ObligationStatus.INCONCLUSIVE, ObligationStatus.HUMAN_REQUIRED}
                ],
            }

            system_instruction = (
                "You are an expert engineering reviewer. Synthesize an evidence-grounded updated implementation plan.\n"
                "CRITICAL OUTPUT-FIDELITY & SEMANTIC RULES:\n"
                "1. Distinguish present repository state from planned future actions. NEVER state that a proposed replacement "
                "or new component already exists in the repository unless verified in authorized_facts.\n"
                "2. `existing_target_files`: MUST list only verified snapshot files that currently exist in the repository.\n"
                "3. `proposed_new_files`: MUST list any new files that need to be created.\n"
                "4. `existing_target_symbols`: MUST list only symbol identifiers (classes, functions, hooks, components) that currently exist in the repository snapshot. NEVER put file paths in existing_target_symbols.\n"
                "5. `proposed_new_symbols`: MUST list any new symbols to be created/introduced (e.g., 'AuthProvider', 'useAuth').\n"
                "6. `unresolved_dependency_ids`: MUST list any unresolved dependencies or obligations lacking repository evidence.\n"
                "7. Fact Grounding: Every PlanChange with KEEP, MODIFY, or REMOVE concerning current repository state MUST cite a valid `basis_fact_id` from authorized_facts or a valid human_decision_id.\n"
                "8. Absence Invariant: Absence of evidence is NOT evidence of absence. If a target file or symbol is unresolved/inconclusive, do NOT claim 'file does not exist' or mark REMOVE unless an explicit AuthorizedFact establishes that negative fact. State: 'The candidate plan\\'s <target> target was not established by the verified snapshot evidence. Resolve the actual implementation target before implementation.' and mark UNRESOLVED.\n"
                "9. ADD may be proposed without present-state basis facts, but must not pretend the artifact exists today.\n"
                "10. If a step relies on unverified dependencies or requires human authority, mark confidence_basis as UNRESOLVED.\n"
                "11. Disproved Target Absence: If an AuthorizedFact with relationship CONTRADICTS establishes that an assumed target path does not exist in the snapshot manifest, do NOT claim the file currently exists and do NOT prescribe modifying an absent file. Instead, emit an advisory action stating that the submitted target path is not present in the verified snapshot, and guide the engineer to create the new module at the proposed path or locate the intended existing module before implementation. Do NOT put absent files in existing_target_files; list them in proposed_new_files if creation is intended.\n"
                "12. OUTPUT FIDELITY BOUNDARY: Do NOT invent unrequested concrete technologies, libraries, auth protocols (e.g., JWT, OAuth, Clerk, Auth0), environment variables (e.g., VITE_APP_NAME), or files not mentioned in the submitted candidate plan or verified in authorized_facts. Use only the names and concepts provided in the candidate plan (e.g., application-owned auth provider, useAuth hook)."
            )

            response: ModelRevisedPlanResponse | None = None
            validation_error: str | None = None
            max_attempts = 2

            try:
                for attempt in range(1, max_attempts + 1):
                    current_payload = dict(prompt_payload)
                    if validation_error:
                        current_payload["semantic_validation_error"] = (
                            f"Your previous revision proposal violated semantic facts: {validation_error}. "
                            f"Fix all structured fields and prose to strictly adhere to authorized facts and snapshot files."
                        )

                    try:
                        candidate_response = await self.gateway.complete_structured(
                            prompt=json.dumps(current_payload, indent=2),
                            schema=ModelRevisedPlanResponse,
                            system=system_instruction,
                            run_id=run_id,
                            purpose="PLAN_REVISION",
                        )
                    except Exception as exc:
                        logger.warning(
                            f"Plan revision model synthesis attempt {attempt} failed safely: {exc}"
                        )
                        break

                    if not candidate_response:
                        break

                    # Validate candidate response structured fields against snapshot and output fidelity
                    validation_issues = []
                    for step in candidate_response.implementation_plan:
                        for fpath in step.existing_target_files:
                            clean_p = fpath.strip().replace("\\", "/")
                            if clean_p and clean_p not in snapshot_files:
                                validation_issues.append(
                                    f"File '{clean_p}' in step {step.order} was listed in existing_target_files, but does not exist in the snapshot"
                                )
                        for sym in step.existing_target_symbols:
                            clean_sym = sym.strip()
                            if _is_path_like(clean_sym):
                                validation_issues.append(
                                    f"Path '{clean_sym}' in step {step.order} was listed in existing_target_symbols. Paths belong in existing_target_files, not symbols."
                                )
                            elif clean_sym not in snapshot_symbols:
                                validation_issues.append(
                                    f"Symbol '{clean_sym}' in step {step.order} was listed in existing_target_symbols, but is not verified in the snapshot. Move new/unverified symbols to proposed_new_symbols."
                                )
                        # Output fidelity checks
                        step_text = f"{step.action} {step.rationale} {' '.join(step.proposed_new_files)} {' '.join(step.proposed_new_symbols)}"
                        for v in _check_output_fidelity(step_text):
                            validation_issues.append(f"Step {step.order} has {v}")

                    for change in candidate_response.plan_changes:
                        ctype_str = change.change_type.upper()
                        valid_facts = [fid for fid in change.basis_fact_ids if fid in fact_map]
                        valid_human = [
                            hid for hid in change.human_decision_ids if hid in valid_human_ids
                        ]
                        if (
                            ctype_str in {"KEEP", "MODIFY", "REMOVE"}
                            and not valid_facts
                            and not valid_human
                        ):
                            if (
                                "does not exist" in change.rationale.lower()
                                or "not in repository" in change.rationale.lower()
                                or ctype_str == "REMOVE"
                            ):
                                validation_issues.append(
                                    f"Plan change for step '{change.source_plan_step_ids}' with change_type '{ctype_str}' asserts a fact ('{change.rationale}') without citing any valid basis_fact_ids. Mark as UNRESOLVED without claiming absence unless an authoritative negative fact exists."
                                )
                        change_text = f"{change.rationale} {change.updated_text or ''}"
                        for v in _check_output_fidelity(change_text):
                            validation_issues.append(
                                f"Plan change for step {change.source_plan_step_ids} has {v}"
                            )

                    if validation_issues and attempt < max_attempts:
                        validation_error = "; ".join(validation_issues)
                        logger.info(
                            f"Plan revision attempt {attempt} semantic validation failed: {validation_error}. Retrying bounded..."
                        )
                        continue

                    response = candidate_response
                    break

                if response:
                    executive_summary = response.executive_summary[:1000]

                    # Validate Plan Changes
                    for raw_change in response.plan_changes:
                        try:
                            ctype = PlanChangeType(raw_change.change_type.upper())
                        except ValueError:
                            ctype = PlanChangeType.MODIFY

                        valid_fact_ids = [
                            fid for fid in raw_change.basis_fact_ids if fid in fact_map
                        ]
                        valid_ev_ids = [
                            eid for eid in raw_change.evidence_ids if eid in valid_fact_evidence_ids
                        ]
                        valid_h_ids = [
                            hid for hid in raw_change.human_decision_ids if hid in valid_human_ids
                        ]

                        rationale = raw_change.rationale

                        # Invariant 1: Factual KEEP/MODIFY/REMOVE without basis facts or human decisions must be UNRESOLVED
                        if (
                            ctype
                            in {PlanChangeType.KEEP, PlanChangeType.MODIFY, PlanChangeType.REMOVE}
                            and not valid_fact_ids
                            and not valid_h_ids
                        ):
                            ctype = PlanChangeType.UNRESOLVED
                            if "not established" not in rationale.lower():
                                target_name = raw_change.original_text or "candidate plan step"
                                rationale = f"The candidate plan's {target_name} target was not established by the verified snapshot evidence. Resolve the actual implementation target before implementation."

                        # Invariant 2: Absence of evidence is not evidence of absence
                        has_contradiction = any(
                            fact_map[fid].relationship == FactRelationship.CONTRADICTS
                            for fid in valid_fact_ids
                        )
                        if not has_contradiction:
                            for pattern in [
                                "does not exist in the repository snapshot per authorized facts",
                                "does not exist in the repository snapshot",
                                "does not exist",
                            ]:
                                if pattern in rationale:
                                    rationale = rationale.replace(
                                        pattern,
                                        "was not established by the verified snapshot evidence",
                                    )

                        plan_changes.append(
                            PlanChange(
                                change_type=ctype,
                                source_plan_step_ids=raw_change.source_plan_step_ids,
                                original_text=raw_change.original_text,
                                updated_text=raw_change.updated_text
                                if ctype != PlanChangeType.UNRESOLVED
                                else None,
                                rationale=rationale,
                                basis_fact_ids=valid_fact_ids,
                                evidence_ids=valid_ev_ids,
                                human_decision_ids=valid_h_ids,
                            )
                        )

                    # Validate Implementation Plan Steps
                    for raw_step in response.implementation_plan:
                        try:
                            stype = PlanChangeType(raw_step.status.upper())
                        except ValueError:
                            stype = PlanChangeType.MODIFY

                        valid_fact_ids = [fid for fid in raw_step.basis_fact_ids if fid in fact_map]
                        valid_ev_ids = [
                            eid
                            for eid in raw_step.supporting_evidence_ids
                            if eid in valid_fact_evidence_ids
                        ]
                        valid_step_human_ids = [
                            hid
                            for hid in raw_step.supporting_human_decision_ids
                            if hid in valid_human_ids
                        ]

                        # Verify existing target files strictly exist in snapshot
                        existing_files: list[str] = []
                        suggested_files: list[str] = []
                        step_has_invalid_existing_file = False

                        for fpath in raw_step.existing_target_files:
                            clean_fpath = fpath.strip().replace("\\", "/")
                            if clean_fpath in snapshot_files:
                                existing_files.append(clean_fpath)
                            else:
                                step_has_invalid_existing_file = True
                                suggested_files.append(clean_fpath)

                        for fpath in raw_step.proposed_new_files:
                            clean_fpath = fpath.strip().replace("\\", "/")
                            if clean_fpath and clean_fpath not in suggested_files:
                                suggested_files.append(clean_fpath)

                        # Verify existing target symbols (reject paths and unverified symbols fail-closed)
                        existing_symbols: list[str] = []
                        proposed_symbols: list[str] = []

                        for sym in raw_step.existing_target_symbols:
                            clean_sym = sym.strip()
                            if not clean_sym or _is_path_like(clean_sym):
                                continue
                            if clean_sym in snapshot_symbols:
                                existing_symbols.append(clean_sym)
                            else:
                                proposed_symbols.append(clean_sym)

                        for sym in raw_step.proposed_new_symbols:
                            clean_sym = sym.strip()
                            if (
                                clean_sym
                                and not _is_path_like(clean_sym)
                                and clean_sym not in proposed_symbols
                            ):
                                proposed_symbols.append(clean_sym)

                        # Handle ungrounded/invalid steps (strictly using valid_step_human_ids)
                        unresolved_deps = list(raw_step.unresolved_dependency_ids)
                        step_text = f"{raw_step.action} {raw_step.rationale} {' '.join(suggested_files)} {' '.join(proposed_symbols)}"
                        step_fid_violations = _check_output_fidelity(step_text)
                        if (
                            step_has_invalid_existing_file
                            or step_fid_violations
                            or (
                                not valid_fact_ids
                                and not valid_step_human_ids
                                and stype not in {PlanChangeType.ADD, PlanChangeType.UNRESOLVED}
                            )
                        ):
                            stype = PlanChangeType.UNRESOLVED

                        # Sanitize negative absence claims in rationale and action
                        has_contradiction = any(
                            fact_map[fid].relationship == FactRelationship.CONTRADICTS
                            for fid in valid_fact_ids
                        )
                        rationale = raw_step.rationale
                        action = raw_step.action

                        if not has_contradiction:
                            for pattern in [
                                "does not exist in the repository snapshot per authorized facts",
                                "does not exist in the repository snapshot",
                                "does not exist",
                            ]:
                                if pattern in rationale:
                                    rationale = rationale.replace(
                                        pattern,
                                        "was not established by the verified snapshot evidence",
                                    )
                                if pattern in action:
                                    action = action.replace(
                                        pattern,
                                        "was not established by the verified snapshot evidence",
                                    )

                        # Determine strict confidence basis
                        if stype == PlanChangeType.UNRESOLVED or step_has_invalid_existing_file:
                            confidence = ConfidenceBasis.UNRESOLVED
                        elif valid_fact_ids and any(
                            fact_map[fid].relationship
                            in {FactRelationship.SUPPORTS, FactRelationship.CONTRADICTS}
                            for fid in valid_fact_ids
                        ):
                            confidence = ConfidenceBasis.EVIDENCE_BACKED
                        elif valid_step_human_ids:
                            confidence = ConfidenceBasis.HUMAN_CONFIRMED
                        elif valid_fact_ids:
                            confidence = ConfidenceBasis.PARTIALLY_EVIDENCED
                        else:
                            confidence = ConfidenceBasis.UNRESOLVED

                        target_syms = list(dict.fromkeys(existing_symbols + proposed_symbols))

                        implementation_plan.append(
                            RevisedPlanStep(
                                order=raw_step.order,
                                action=action,
                                rationale=rationale,
                                status=stype,
                                source_plan_step_ids=raw_step.source_plan_step_ids,
                                basis_fact_ids=valid_fact_ids,
                                supporting_obligation_ids=raw_step.supporting_obligation_ids,
                                supporting_evidence_ids=valid_ev_ids,
                                supporting_human_decision_ids=valid_step_human_ids,
                                unresolved_dependency_ids=unresolved_deps,
                                existing_target_files=existing_files,
                                proposed_new_files=suggested_files,
                                existing_target_symbols=existing_symbols,
                                proposed_new_symbols=proposed_symbols,
                                target_symbols=target_syms,
                                confidence_basis=confidence,
                            )
                        )
            except Exception as exc:
                logger.warning(f"Plan revision model synthesis failed safely: {exc}")
                final_status = RevisedPlanStatus.UNAVAILABLE
                executive_summary = (
                    "Verification completed, but updated-plan synthesis was unavailable."
                )

        # If model failed or no plan produced, create safe fallback entry
        if not implementation_plan and final_status != RevisedPlanStatus.UNAVAILABLE:
            final_status = RevisedPlanStatus.UNAVAILABLE
            executive_summary = (
                "Verification completed, but updated-plan synthesis was unavailable."
            )

        revised_plan = RevisedPlan(
            run_id=run_id,
            project_id=project_id,
            snapshot_id=snapshot_id,
            original_plan_version_id=plan_version.id,
            revision_version=revision_version,
            status=final_status,
            executive_summary=executive_summary,
            plan_changes=plan_changes,
            implementation_plan=implementation_plan,
            model_call_id=model_call_id,
        )

        saved = await self.repository.create(revised_plan)
        logger.info(
            "Saved revised plan id=%s run_id=%s version=%s status=%s steps=%d",
            saved.id,
            run_id,
            saved.revision_version,
            saved.status,
            len(saved.implementation_plan),
        )
        return saved
