from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.db.mongo import MongoManager
from app.domain.revised_plans import RevisedPlan


class RevisedPlansRepository:
    def __init__(self, mongo: MongoManager | AsyncDatabase | Any) -> None:
        if isinstance(mongo, MongoManager):
            self._database = mongo.database()
        elif isinstance(mongo, AsyncDatabase):
            self._database = mongo
        elif hasattr(mongo, "database") and callable(getattr(mongo, "database", None)):
            self._database = mongo.database()
        else:
            self._database = mongo

    async def create(self, revised_plan: RevisedPlan) -> RevisedPlan:
        await self._database.revised_plans.insert_one(revised_plan.model_dump(mode="python"))
        return revised_plan

    async def get_latest(self, run_id: str) -> RevisedPlan | None:
        doc = await self._database.revised_plans.find_one(
            {"run_id": run_id}, sort=[("revision_version", -1)]
        )
        return RevisedPlan.model_validate(doc) if doc else None

    async def list_for_run(self, run_id: str) -> list[RevisedPlan]:
        cursor = self._database.revised_plans.find({"run_id": run_id}).sort(
            "revision_version", 1
        )
        return [RevisedPlan.model_validate(doc) async for doc in cursor]
