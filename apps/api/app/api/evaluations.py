from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_mongo
from app.db.mongo import MongoManager

router = APIRouter(prefix="/v1/evaluations", tags=["evaluations"])


def _safe_document(item: dict) -> dict:
    item.pop("_id", None)
    return item


@router.get("/latest")
async def latest_evaluation(mongo: Annotated[MongoManager, Depends(get_mongo)]):
    """Expose measured evaluator output, never case expectations or hidden prompts."""
    item = await mongo.database().eval_runs.find_one({}, sort=[("timestamp", -1)])
    if not item:
        raise HTTPException(404, "no evaluation runs recorded")
    return _safe_document(item)
