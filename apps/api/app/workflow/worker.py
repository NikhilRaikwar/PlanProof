import asyncio

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from app.core.config import Settings
from app.db.mongo import MongoManager
from app.repositories.runs import RunRepository
from app.repositories.verification import VerificationRepository
from app.workflow.engine import VerificationWorkflow

_settings = Settings()
dramatiq.set_broker(RedisBroker(url=_settings.redis_url.get_secret_value()))


@dramatiq.actor(max_retries=3, min_backoff=1000)
def execute_verification_run(run_id: str) -> None:
    asyncio.run(_execute(run_id))


async def _execute(run_id: str) -> None:
    mongo = MongoManager(_settings)
    await mongo.connect()
    try:
        await VerificationWorkflow(
            RunRepository(mongo), VerificationRepository(mongo), _settings
        ).run(run_id)
    finally:
        await mongo.close()
