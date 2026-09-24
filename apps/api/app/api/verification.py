from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import (
    get_authorized_project,
    get_mongo,
    get_quota_service,
    get_settings_dep,
    require_session,
    verify_tenant_project_access,
)
from app.core.config import Settings
from app.db.mongo import MongoManager
from app.domain.runs import PlanVersion
from app.repositories.runs import RunRepository
from app.repositories.verification import VerificationRepository
from app.services.models import ProviderGateway
from app.services.obligations import ObligationExtractionService
from app.services.quotas import QuotaService
from app.services.repository_tools import (
    FindSymbolInput,
    ListFilesInput,
    ReadFileRangeInput,
    RepositoryTools,
    SearchCodeInput,
)

router = APIRouter(prefix="/v1", tags=["verification"])


class CreatePlanRequest(BaseModel):
    change_request: str = Field(min_length=1, max_length=20_000)
    candidate_plan: str = Field(min_length=1, max_length=50_000)
    parent_plan_version_id: str | None = None


class ExtractRequest(BaseModel):
    snapshot_id: str


class ToolRequest(BaseModel):
    tool: Literal[
        "list_files", "search_code_lexical", "read_file_range", "find_symbol", "find_references"
    ]
    input: dict


@router.post("/projects/{project_id}/plan-versions", response_model=PlanVersion)
async def create_plan(
    project_id: str,
    request: CreatePlanRequest,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    session: Annotated[dict, Depends(require_session)],
):
    await get_authorized_project(project_id, mongo, session)
    records = RunRepository(mongo)
    count = await mongo.database().plan_versions.count_documents({"project_id": project_id})
    item = PlanVersion(project_id=project_id, version=count + 1, **request.model_dump())
    return await records.create_plan_version(item)


@router.post("/plan-versions/{plan_version_id}/extract-obligations")
async def extract(
    plan_version_id: str,
    request: ExtractRequest,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    session: Annotated[dict, Depends(require_session)],
    quota_service: Annotated[QuotaService, Depends(get_quota_service)],
):
    # Disable low-level direct extraction route in production
    if settings.planproof_env == "production":
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "direct extraction debug route is disabled in production"
        )

    records = RunRepository(mongo)
    plan = await records.get_plan_version(plan_version_id)
    snapshot = await records.get_snapshot(request.snapshot_id)
    if (
        not plan
        or not snapshot
        or snapshot.project_id != plan.project_id
        or snapshot.status != "READY"
    ):
        raise HTTPException(422, "plan and READY snapshot must belong to the same project")

    await get_authorized_project(plan.project_id, mongo, session)

    account_key = str(session.get("installation_id") or session["account_login"])
    reserved = await quota_service.reserve_verification_run_quota(
        account_key, session["account_login"]
    )
    try:
        repo = VerificationRepository(mongo)
        service = ObligationExtractionService(ProviderGateway(settings, repo), repo)
        return await service.extract(
            plan.project_id,
            snapshot.id,
            plan.id,
            plan.change_request,
            plan.candidate_plan,
            normalized_steps=plan.normalized_steps,
        )
    finally:
        await quota_service.rollback_verification_run_quota(reserved)


@router.post("/tools/execute")
async def execute_tool(
    request: ToolRequest,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    session: Annotated[dict, Depends(require_session)],
):
    # Disable public tool execution in production
    if settings.planproof_env == "production":
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "tool execution debug route is disabled in production"
        )

    # In dev/test, verify snapshot exists and belongs to authenticated tenant
    snapshot_id = request.input.get("snapshot_id")
    if not snapshot_id:
        raise HTTPException(422, "snapshot_id is required in tool input")
    snapshot = await RunRepository(mongo).get_snapshot(snapshot_id)
    if not snapshot:
        raise HTTPException(404, "snapshot not found")
    await get_authorized_project(snapshot.project_id, mongo, session)

    tools = RepositoryTools(RunRepository(mongo), VerificationRepository(mongo))
    models = {
        "list_files": ListFilesInput,
        "search_code_lexical": SearchCodeInput,
        "read_file_range": ReadFileRangeInput,
        "find_symbol": FindSymbolInput,
        "find_references": FindSymbolInput,
    }
    try:
        return await getattr(tools, request.tool)(
            models[request.tool].model_validate(request.input)
        )
    except ValueError as exc:
        raise HTTPException(422, "invalid tool request") from exc


@router.get("/proof-obligations/{item_id}")
async def get_obligation(
    item_id: str,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    session: Annotated[dict, Depends(require_session)],
):
    item = await VerificationRepository(mongo).get_obligation(item_id)
    if not item:
        raise HTTPException(404, "proof obligation not found")
    project = await mongo.database().projects.find_one({"id": item.project_id})
    if not project:
        raise HTTPException(404, "proof obligation not found")
    verify_tenant_project_access(project, session)
    return item


@router.get("/evidence/{item_id}")
async def get_evidence(
    item_id: str,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    session: Annotated[dict, Depends(require_session)],
):
    item = await VerificationRepository(mongo).get_evidence(item_id)
    if not item:
        raise HTTPException(404, "evidence not found")
    snapshot = await mongo.database().repository_snapshots.find_one({"id": item.snapshot_id})
    if not snapshot:
        raise HTTPException(404, "evidence not found")
    project = await mongo.database().projects.find_one({"id": snapshot.get("project_id")})
    if not project:
        raise HTTPException(404, "evidence not found")
    verify_tenant_project_access(project, session)
    return item
