import asyncio
import logging

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from app.core.config import Settings
from app.db.mongo import MongoManager
from app.domain.runs import VerificationRunStatus
from app.repositories.runs import RunRepository
from app.repositories.verification import VerificationRepository
from app.workflow.engine import VerificationWorkflow

logger = logging.getLogger(__name__)

_settings = Settings()
# Development/test imports may not configure Redis because no job is executed.
# Production Settings rejects that state before this module can be used.
_broker_url = (
    _settings.redis_url.get_secret_value()
    if _settings.redis_is_configured
    else "redis://127.0.0.1:6379/0"
)
dramatiq.set_broker(RedisBroker(url=_broker_url))


@dramatiq.actor(max_retries=3, min_backoff=1000)
def execute_verification_run(run_id: str) -> None:
    asyncio.run(_execute(run_id))


async def _execute(run_id: str) -> None:
    mongo = MongoManager(_settings)
    await mongo.connect()
    try:
        run_doc = await mongo.database().verification_runs.find_one({"id": run_id})
        if not run_doc:
            return
        terminal_statuses = {
            VerificationRunStatus.COMPLETE.value,
            VerificationRunStatus.BLOCKED.value,
            VerificationRunStatus.INCONCLUSIVE.value,
            VerificationRunStatus.FAILED.value,
            VerificationRunStatus.HUMAN_DECISION_REQUIRED.value,
        }
        if run_doc.get("status") in terminal_statuses:
            logger.info("run_duplicate_delivery_ignored run_id=%s status=%s", run_id, run_doc.get("status"))
            return

        await VerificationWorkflow(
            RunRepository(mongo), VerificationRepository(mongo), _settings
        ).run(run_id)
    finally:
        try:
            from app.services.quotas import QuotaService

            await QuotaService(mongo.database(), _settings).release_active_reservation(run_id)
        except Exception:
            pass
        await mongo.close()
