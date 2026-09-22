import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.dependencies import get_mongo, get_settings_dep
from app.api.github import get_optional_session
from app.core.config import Settings
from app.db.mongo import MongoManager
from app.domain.runs import (
    HumanQuestionStatus,
    PlanVersion,
    RunEvent,
    VerificationRun,
    VerificationRunStatus,
)
from app.domain.verification import ObligationStatus
from app.repositories.projects import ProjectsRepository
from app.repositories.runs import RunRepository
from app.repositories.verification import VerificationRepository
from app.workflow.worker import execute_verification_run

router = APIRouter(prefix="/v1", tags=["workflow"])


def _safe_document(item: dict) -> dict:
    """Mongo's internal ObjectId is not API data."""
    item.pop("_id", None)
    return item


class CreateRunRequest(BaseModel):
    project_id: str
    snapshot_id: str
    plan_version_id: str


class HumanAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=5000)
    actor_id: str = Field(min_length=1, max_length=200)


class AmendmentRequest(BaseModel):
    candidate_plan: str = Field(min_length=1, max_length=50_000)


class RunRepositoryContext(BaseModel):
    id: str
    name: str
    full_name: str | None = None
    repository_source_type: str


class RunSnapshotContext(BaseModel):
    id: str
    requested_ref: str | None = None
    resolved_commit_sha: str | None = None
    status: str


class RunPlanContext(BaseModel):
    id: str
    version: int
    change_request: str


async def _verify_tenant_project_access(project: dict, session: dict | None) -> None:
    if not session:
        return
    proj_inst_id = project.get("github_installation_id")
    if proj_inst_id is not None:
        if proj_inst_id != session.get("installation_id"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "verification run not found")
        return
    if project.get("owner_id") != session.get("account_login"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "verification run not found")


async def _get_authorized_run(
    run_id: str,
    mongo: MongoManager,
    session: dict | None,
) -> tuple[VerificationRun, dict]:
    run = await RunRepository(mongo).get_run(run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "verification run not found")
    project = await mongo.database().projects.find_one({"id": run.project_id})
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "verification run not found")
    await _verify_tenant_project_access(project, session)
    return run, project


async def _resolve_run_tools(database, run: VerificationRun) -> tuple[list[dict], str]:
    # 1. Exact match by run_id
    exact_cursor = database.tool_runs.find({"run_id": run.id}).sort("started_at", 1)
    tools = [item async for item in exact_cursor]
    if tools:
        return tools, "EXACT"

    # 2. Legacy reconstruction ONLY through evidence IDs linked to run's obligations
    obligations = [item async for item in database.proof_obligations.find({"run_id": run.id})]
    evidence_ids: list[str] = []
    for ob in obligations:
        evidence_ids.extend(ob.get("evidence_ids", []))
        evidence_ids.extend(ob.get("counter_evidence_ids", []))

    if evidence_ids:
        ev_cursor = database.evidence.find({"id": {"$in": evidence_ids}})
        source_tool_ids = list(
            {item["source_tool_run_id"] async for item in ev_cursor if item.get("source_tool_run_id")}
        )
        if source_tool_ids:
            legacy_cursor = database.tool_runs.find({"id": {"$in": source_tool_ids}}).sort(
                "started_at", 1
            )
            tools = [item async for item in legacy_cursor]
            return tools, "LEGACY_EVIDENCE_RECONSTRUCTED"

    # 3. Explicitly unavailable - NEVER fall back to snapshot-wide query
    attribution_status = (
        "LEGACY_TRACE_UNAVAILABLE" if run.tool_call_count > 0 else "NO_TOOLS_EXECUTED"
    )
    return [], attribution_status


@router.get("/verification-runs")
async def list_verification_runs(
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    project_id: str | None = None,
    planproof_session: Annotated[str | None, Cookie()] = None,
):
    session = await get_optional_session(mongo, settings, planproof_session)
    database = mongo.database()
    query: dict[str, Any] = {}

    if session:
        if project_id:
            project = await database.projects.find_one({"id": project_id})
            if not project:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
            await _verify_tenant_project_access(project, session)
            query["project_id"] = project_id
        else:
            user_projects = [
                p["id"]
                async for p in database.projects.find(
                    {"owner_id": session["account_login"], "data_scope": "USER"}
                )
            ]
            query["project_id"] = {"$in": user_projects}
    elif project_id:
        query["project_id"] = project_id

    cursor = database.verification_runs.find(query).sort("created_at", -1).limit(100)
    runs: list[VerificationRun] = []
    async for item in cursor:
        run = VerificationRun.model_validate(item)
        if not run.plan_title:
            plan = await database.plan_versions.find_one({"id": run.plan_version_id})
            if plan:
                run.plan_title = plan.get("change_request", "")[:100]
        if not run.commit_sha:
            snap = await database.repository_snapshots.find_one({"id": run.snapshot_id})
            if snap:
                run.commit_sha = snap.get("resolved_commit_sha")
                run.ref = snap.get("requested_ref")
        run.has_open_human_question = bool(run.open_human_question_ids)
        runs.append(run)

    return runs


@router.post(
    "/verification-runs", response_model=VerificationRun, status_code=status.HTTP_202_ACCEPTED
)
async def create_verification_run(
    request_obj: Request,
    request: CreateRunRequest,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    planproof_session: Annotated[str | None, Cookie()] = None,
) -> VerificationRun:
    session = await get_optional_session(mongo, settings, planproof_session)
    runs = RunRepository(mongo)
    project = await ProjectsRepository(mongo).get(request.project_id)
    if not project:
        raise HTTPException(404, "project, snapshot, or plan version not found")

    if not session:
        if str(project.data_scope) == "USER" or project.github_installation_id or project.owner_id:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required to verify project")
    else:
        await _verify_tenant_project_access(project.model_dump(), session)

    tenant_key = f"rate:run:{session['installation_id']}" if session else f"rate:run:{project.id}"
    try:
        redis = request_obj.app.state.redis
        allowed = await redis.consume_rate_limit(tenant_key, max_requests=10, window_seconds=60)
        if not allowed:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "verification run rate limit exceeded for this account (max 10 per minute)",
            )
    except HTTPException:
        raise
    except Exception:
        pass

    active_query = {
        "project_id": project.id,
        "status": {
            "$in": [
                VerificationRunStatus.QUEUED.value,
                VerificationRunStatus.EXTRACTING_OBLIGATIONS.value,
                VerificationRunStatus.VERIFYING.value,
                VerificationRunStatus.HUMAN_WAIT.value,
                VerificationRunStatus.FINALIZING.value,
            ]
        },
    }
    active_count = await mongo.database().verification_runs.count_documents(active_query)
    if active_count >= 3:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "concurrent verification run limit reached for this project (max 3 active runs)",
        )

    snapshot = await runs.get_snapshot(request.snapshot_id)
    plan = await runs.get_plan_version(request.plan_version_id)
    if not snapshot or not plan:
        raise HTTPException(404, "project, snapshot, or plan version not found")
    if (
        snapshot.status != "READY"
        or snapshot.project_id != project.id
        or plan.project_id != project.id
    ):
        raise HTTPException(422, "run inputs must belong to the project and snapshot must be READY")
    if idempotency_key:
        existing = await mongo.database().verification_runs.find_one(
            {"idempotency_key": idempotency_key}
        )
        if existing:
            return VerificationRun.model_validate(existing)
    run = VerificationRun(
        project_id=project.id,
        snapshot_id=snapshot.id,
        plan_version_id=plan.id,
        status=VerificationRunStatus.QUEUED,
        idempotency_key=idempotency_key,
    )
    await runs.create_run(run)
    await runs.append_event(
        RunEvent(
            run_id=run.id, sequence=1, event_type="run_created", summary="Verification run queued"
        )
    )
    execute_verification_run.send(run.id)
    return run


@router.get("/verification-runs/{run_id}")
async def get_verification_run(
    run_id: str,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    planproof_session: Annotated[str | None, Cookie()] = None,
):
    session = await get_optional_session(mongo, settings, planproof_session)
    run, project = await _get_authorized_run(run_id, mongo, session)
    database = mongo.database()
    runs_repo = RunRepository(mongo)

    snapshot = await runs_repo.get_snapshot(run.snapshot_id)
    plan = await runs_repo.get_plan_version(run.plan_version_id)

    count_cursor = await database.proof_obligations.aggregate(
        [{"$match": {"run_id": run.id}}, {"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    )
    counts = {item["_id"]: item["count"] async for item in count_cursor}

    questions = [
        {
            "id": item["id"],
            "status": item["status"],
            "obligation_id": item["obligation_id"],
            "question": item["question"],
            "why_needed": item["why_needed"],
            "authority_required": item["authority_required"],
            "answer": item.get("answer"),
            "answered_at": item.get("answered_at"),
        }
        async for item in database.human_questions.find({"run_id": run.id})
    ]

    tools, trace_attribution_status = await _resolve_run_tools(database, run)

    # Calculate exact evidence count from run's obligations
    obligations = [item async for item in database.proof_obligations.find({"run_id": run.id})]
    run_evidence_ids = set()
    for ob in obligations:
        run_evidence_ids.update(ob.get("evidence_ids", []))
        run_evidence_ids.update(ob.get("counter_evidence_ids", []))

    return {
        "run": run,
        "repository": RunRepositoryContext(
            id=project["id"],
            name=project["name"],
            full_name=(
                (project.get("repository_url") or "").split("github.com/")[-1]
                if project.get("repository_url")
                else project["name"]
            ),
            repository_source_type=str(project.get("repository_source_type", "")),
        ),
        "snapshot": RunSnapshotContext(
            id=snapshot.id if snapshot else run.snapshot_id,
            requested_ref=snapshot.requested_ref if snapshot else None,
            resolved_commit_sha=snapshot.resolved_commit_sha if snapshot else None,
            status=snapshot.status if snapshot else "UNKNOWN",
        ),
        "plan": RunPlanContext(
            id=plan.id if plan else run.plan_version_id,
            version=plan.version if plan else 1,
            change_request=plan.change_request if plan else "",
        ),
        "obligation_counts": counts,
        "human_questions": questions,
        "tool_runs": [_safe_document(item) for item in tools],
        "evidence_count": len(run_evidence_ids),
        "tool_execution_count": len(tools),
        "trace_attribution_status": trace_attribution_status,
    }


@router.get("/verification-runs/{run_id}/proof-obligations")
async def list_run_obligations(
    run_id: str,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    planproof_session: Annotated[str | None, Cookie()] = None,
):
    session = await get_optional_session(mongo, settings, planproof_session)
    await _get_authorized_run(run_id, mongo, session)
    cursor = mongo.database().proof_obligations.find({"run_id": run_id}).sort("created_at", 1)
    return [_safe_document(item) async for item in cursor]


@router.get("/verification-runs/{run_id}/evidence")
async def list_run_evidence(
    run_id: str,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    planproof_session: Annotated[str | None, Cookie()] = None,
):
    session = await get_optional_session(mongo, settings, planproof_session)
    run, _ = await _get_authorized_run(run_id, mongo, session)
    database = mongo.database()

    # Collect evidence IDs from this run's obligations
    obligations = [item async for item in database.proof_obligations.find({"run_id": run.id})]
    run_evidence_ids: list[str] = []
    obligation_by_evidence: dict[str, dict] = {}
    for ob in obligations:
        for ev_id in ob.get("evidence_ids", []):
            run_evidence_ids.append(ev_id)
            obligation_by_evidence[ev_id] = {
                "obligation_id": ob["id"],
                "statement": ob["statement"],
                "relationship": "SUPPORTS",
            }
        for ev_id in ob.get("counter_evidence_ids", []):
            run_evidence_ids.append(ev_id)
            obligation_by_evidence[ev_id] = {
                "obligation_id": ob["id"],
                "statement": ob["statement"],
                "relationship": "CONTRADICTS",
            }

    if not run_evidence_ids:
        return []

    cursor = database.evidence.find({"id": {"$in": run_evidence_ids}}).sort("created_at", 1)
    evidence_items = []
    async for item in cursor:
        _safe_document(item)
        snapshot_id = item.get("snapshot_id")
        path = item.get("path")
        start_line = item.get("line_start")
        end_line = item.get("line_end")
        content_hash = item.get("content_hash")

        snippet = None
        if path and start_line is not None and end_line is not None:
            file_doc = await database.repository_files.find_one(
                {"snapshot_id": snapshot_id, "path": path}
            )
            if file_doc:
                if not content_hash or file_doc.get("content_hash") == content_hash:
                    lines = file_doc.get("text", "").splitlines()
                    snippet = "\n".join(lines[max(0, start_line - 1) : end_line])

        item["start_line"] = start_line
        item["end_line"] = end_line
        item["safe_fact_summary"] = item.get("summary", "")
        item["snippet"] = snippet
        ob_info = obligation_by_evidence.get(item.get("id"))
        if ob_info:
            item["obligation_id"] = ob_info["obligation_id"]
            item["obligation_statement"] = ob_info["statement"]
            item["relationship"] = ob_info["relationship"]

        evidence_items.append(item)

    return evidence_items


@router.get("/verification-runs/{run_id}/tool-runs")
async def list_run_tool_runs(
    run_id: str,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    planproof_session: Annotated[str | None, Cookie()] = None,
):
    session = await get_optional_session(mongo, settings, planproof_session)
    run, _ = await _get_authorized_run(run_id, mongo, session)
    tools, _ = await _resolve_run_tools(mongo.database(), run)
    return [_safe_document(item) for item in tools]


@router.get("/verification-runs/{run_id}/events")
async def get_run_events(
    run_id: str,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    last_event_id: Annotated[int, Header(alias="Last-Event-ID")] = 0,
    planproof_session: Annotated[str | None, Cookie()] = None,
):
    session = await get_optional_session(mongo, settings, planproof_session)
    await _get_authorized_run(run_id, mongo, session)
    events = await RunRepository(mongo).list_events(run_id, last_event_id)

    async def stream():
        for event in events:
            payload = json.dumps({"type": event.event_type, "summary": event.summary})
            yield f"id: {event.sequence}\nevent: {event.event_type}\ndata: {payload}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/human-questions/{question_id}/answers", status_code=status.HTTP_202_ACCEPTED)
async def answer_human_question(
    question_id: str,
    request: HumanAnswerRequest,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    planproof_session: Annotated[str | None, Cookie()] = None,
):
    session = await get_optional_session(mongo, settings, planproof_session)
    runs = RunRepository(mongo)
    question = await runs.get_question(question_id)
    if not question:
        raise HTTPException(404, "human question not found")
    run = await runs.get_run(question.run_id)
    if not run:
        raise HTTPException(404, "run not found")
    project = await mongo.database().projects.find_one({"id": run.project_id})
    if project:
        await _verify_tenant_project_access(project, session)

    if question.status == HumanQuestionStatus.ANSWERED:
        if question.answer == request.answer and question.actor_id == request.actor_id:
            return question
        raise HTTPException(409, "human question was already answered")
    if run.status != VerificationRunStatus.HUMAN_WAIT:
        raise HTTPException(409, "run is not waiting for this answer")
    question.status = HumanQuestionStatus.ANSWERED
    question.answer, question.actor_id, question.answered_at = (
        request.answer,
        request.actor_id,
        datetime.now(UTC),
    )
    await runs.update_question(question)
    obligation_repo = VerificationRepository(mongo)
    obligation = await obligation_repo.get_obligation(question.obligation_id)
    obligation.status = ObligationStatus.VERIFIED
    await obligation_repo.update_obligation(obligation)
    run.open_human_question_ids = [
        item for item in run.open_human_question_ids if item != question.id
    ]
    run.completed_obligation_ids.append(obligation.id)
    run.status = VerificationRunStatus.QUEUED
    await runs.update_run(run)
    latest = await mongo.database().events.find_one({"run_id": run.id}, sort=[("sequence", -1)])
    await runs.append_event(
        RunEvent(
            run_id=run.id,
            sequence=(latest["sequence"] if latest else 0) + 1,
            event_type="human_answered",
            summary="Human authority answer persisted; workflow re-queued",
        )
    )
    execute_verification_run.send(run.id)
    return question


@router.post("/plan-versions/{plan_version_id}/amendments", response_model=PlanVersion)
async def accept_amendment(
    plan_version_id: str,
    request: AmendmentRequest,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    planproof_session: Annotated[str | None, Cookie()] = None,
):
    session = await get_optional_session(mongo, settings, planproof_session)
    runs = RunRepository(mongo)
    parent = await runs.get_plan_version(plan_version_id)
    if not parent:
        raise HTTPException(404, "plan version not found")
    project = await mongo.database().projects.find_one({"id": parent.project_id})
    if project:
        await _verify_tenant_project_access(project, session)
    version = (
        await mongo.database().plan_versions.count_documents({"project_id": parent.project_id}) + 1
    )
    amended = PlanVersion(
        project_id=parent.project_id,
        version=version,
        change_request=parent.change_request,
        candidate_plan=request.candidate_plan,
        parent_plan_version_id=parent.id,
    )
    return await runs.create_plan_version(amended)
