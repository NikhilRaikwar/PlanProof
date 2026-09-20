import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.dependencies import get_mongo
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


class CreateRunRequest(BaseModel):
    project_id: str
    snapshot_id: str
    plan_version_id: str


class HumanAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=5000)
    actor_id: str = Field(min_length=1, max_length=200)


class AmendmentRequest(BaseModel):
    candidate_plan: str = Field(min_length=1, max_length=50_000)


@router.get("/verification-runs")
async def list_verification_runs(mongo: Annotated[MongoManager, Depends(get_mongo)]):
    cursor = mongo.database().verification_runs.find({}).sort("created_at", -1).limit(100)
    return [VerificationRun.model_validate(item) async for item in cursor]


@router.post(
    "/verification-runs", response_model=VerificationRun, status_code=status.HTTP_202_ACCEPTED
)
async def create_verification_run(
    request: CreateRunRequest,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> VerificationRun:
    runs = RunRepository(mongo)
    project = await ProjectsRepository(mongo).get(request.project_id)
    snapshot = await runs.get_snapshot(request.snapshot_id)
    plan = await runs.get_plan_version(request.plan_version_id)
    if not project or not snapshot or not plan:
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
async def get_verification_run(run_id: str, mongo: Annotated[MongoManager, Depends(get_mongo)]):
    run = await RunRepository(mongo).get_run(run_id)
    if not run:
        raise HTTPException(404, "verification run not found")
    database = mongo.database()
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
        }
        async for item in database.human_questions.find({"run_id": run.id})
    ]
    tools = [
        {
            "id": item["id"],
            "tool_name": item["tool_name"],
            "status": item["status"],
            "result_count": item["result_count"],
        }
        async for item in database.tool_runs.find({"snapshot_id": run.snapshot_id}).limit(50)
    ]
    return {
        "run": run,
        "obligation_counts": counts,
        "human_questions": questions,
        "tool_runs": tools,
        "evidence_count": await database.evidence.count_documents({"snapshot_id": run.snapshot_id}),
    }


@router.get("/verification-runs/{run_id}/proof-obligations")
async def list_run_obligations(run_id: str, mongo: Annotated[MongoManager, Depends(get_mongo)]):
    if not await RunRepository(mongo).get_run(run_id):
        raise HTTPException(404, "verification run not found")
    cursor = mongo.database().proof_obligations.find({"run_id": run_id}).sort("created_at", 1)
    return [item async for item in cursor]


@router.get("/verification-runs/{run_id}/evidence")
async def list_run_evidence(run_id: str, mongo: Annotated[MongoManager, Depends(get_mongo)]):
    run = await RunRepository(mongo).get_run(run_id)
    if not run:
        raise HTTPException(404, "verification run not found")
    cursor = mongo.database().evidence.find({"snapshot_id": run.snapshot_id}).sort("created_at", 1)
    return [item async for item in cursor]


@router.get("/verification-runs/{run_id}/tool-runs")
async def list_run_tool_runs(run_id: str, mongo: Annotated[MongoManager, Depends(get_mongo)]):
    run = await RunRepository(mongo).get_run(run_id)
    if not run:
        raise HTTPException(404, "verification run not found")
    cursor = mongo.database().tool_runs.find({"snapshot_id": run.snapshot_id}).sort("started_at", 1)
    return [item async for item in cursor]


@router.get("/verification-runs/{run_id}/events")
async def get_run_events(
    run_id: str,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    last_event_id: Annotated[int, Header(alias="Last-Event-ID")] = 0,
):
    if not await RunRepository(mongo).get_run(run_id):
        raise HTTPException(404, "verification run not found")
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
):
    runs = RunRepository(mongo)
    question = await runs.get_question(question_id)
    if not question:
        raise HTTPException(404, "human question not found")
    if question.status == HumanQuestionStatus.ANSWERED:
        if question.answer == request.answer and question.actor_id == request.actor_id:
            return question
        raise HTTPException(409, "human question was already answered")
    run = await runs.get_run(question.run_id)
    if not run or run.status != VerificationRunStatus.HUMAN_WAIT:
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
):
    runs = RunRepository(mongo)
    parent = await runs.get_plan_version(plan_version_id)
    if not parent:
        raise HTTPException(404, "plan version not found")
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
