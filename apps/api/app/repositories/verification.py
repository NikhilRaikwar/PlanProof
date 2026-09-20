from app.db.mongo import MongoManager
from app.domain.verification import Evidence, ModelCall, ProofObligation, ToolRun


class VerificationRepository:
    def __init__(self, mongo: MongoManager) -> None:
        self.database = mongo.database()

    async def create_tool_run(self, item: ToolRun) -> ToolRun:
        await self.database.tool_runs.insert_one(item.model_dump(mode="python"))
        return item

    async def get_tool_run(self, item_id: str) -> ToolRun | None:
        item = await self.database.tool_runs.find_one({"id": item_id})
        return ToolRun.model_validate(item) if item else None

    async def create_evidence(self, item: Evidence) -> Evidence:
        await self.database.evidence.insert_one(item.model_dump(mode="python"))
        return item

    async def create_model_call(self, item: ModelCall) -> ModelCall:
        await self.database.model_calls.insert_one(item.model_dump(mode="python"))
        return item

    async def create_obligation(self, item: ProofObligation) -> ProofObligation:
        await self.database.proof_obligations.update_one(
            {
                "plan_version_id": item.plan_version_id,
                "normalized_statement": item.normalized_statement,
            },
            {"$setOnInsert": item.model_dump(mode="python")},
            upsert=True,
        )
        document = await self.database.proof_obligations.find_one(
            {
                "plan_version_id": item.plan_version_id,
                "normalized_statement": item.normalized_statement,
            }
        )
        return ProofObligation.model_validate(document)
