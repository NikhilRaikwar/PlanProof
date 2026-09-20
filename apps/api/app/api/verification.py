from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.dependencies import get_mongo
from app.core.config import get_settings
from app.db.mongo import MongoManager
from app.domain.runs import PlanVersion
from app.repositories.projects import ProjectsRepository
from app.repositories.runs import RunRepository
from app.repositories.verification import VerificationRepository
from app.services.models import ProviderGateway
from app.services.obligations import ObligationExtractionService
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
    project_id: str, request: CreatePlanRequest, mongo: Annotated[MongoManager, Depends(get_mongo)]
):
    if not await ProjectsRepository(mongo).get(project_id):
        raise HTTPException(404, "project not found")
    records = RunRepository(mongo)
    count = await mongo.database().plan_versions.count_documents({"project_id": project_id})
    item = PlanVersion(project_id=project_id, version=count + 1, **request.model_dump())
    return await records.create_plan_version(item)


@router.post("/plan-versions/{plan_version_id}/extract-obligations")
async def extract(
    plan_version_id: str,
    request: ExtractRequest,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
):
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
    repo = VerificationRepository(mongo)
    service = ObligationExtractionService(ProviderGateway(get_settings(), repo), repo)
    return await service.extract(
        plan.project_id, snapshot.id, plan.id, plan.change_request, plan.candidate_plan
    )


@router.post("/tools/execute")
async def execute_tool(request: ToolRequest, mongo: Annotated[MongoManager, Depends(get_mongo)]):
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
async def get_obligation(item_id: str, mongo: Annotated[MongoManager, Depends(get_mongo)]):
    item = await VerificationRepository(mongo).get_obligation(item_id)
    if not item:
        raise HTTPException(404, "proof obligation not found")
    return item


@router.get("/evidence/{item_id}")
async def get_evidence(item_id: str, mongo: Annotated[MongoManager, Depends(get_mongo)]):
    item = await VerificationRepository(mongo).get_evidence(item_id)
    if not item:
        raise HTTPException(404, "evidence not found")
    return item
