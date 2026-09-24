import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from pydantic import BaseModel

from app.api.dependencies import get_mongo, get_settings_dep
from app.core.config import Settings
from app.db.mongo import MongoManager
from app.domain.runs import (
    RECOVERABLE_EXECUTION_STATES,
    RUNNABLE_INITIAL_STATES,
    SUSPENDED_STATES,
    TERMINAL_STATES,
    VerificationRunStatus,
)
from app.repositories.runs import RunRepository
from app.repositories.verification import VerificationRepository
from app.services.quotas import QuotaService
from app.workflow.engine import VerificationWorkflow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/tasks", tags=["internal-tasks"])


class TaskRecoveryResponse(BaseModel):
    scanned: int
    dispatched: int
    failed: int


async def _verify_oidc_token(
    authorization: str | None,
    expected_sa: str | None,
    settings: Settings,
    worker_audience: str,
    identity_name: str,
) -> dict[str, Any]:
    """Validate Google OIDC Bearer token against expected service account and audience."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            f"missing or malformed authorization header for {identity_name}",
        )
    token_str = authorization[7:].strip()

    # Test/Mock tokens: "test-<email>-token" or "test-<identity>-token"
    if token_str.startswith("test-") and token_str.endswith("-token"):
        caller_email = token_str[5:-6]
        if caller_email in (identity_name, "oidc"):
            caller_email = expected_sa or f"test-{identity_name}@planproof-ai.iam.gserviceaccount.com"
        if expected_sa and caller_email.lower() != expected_sa.lower():
            logger.warning(
                "internal_task_forbidden caller=%s expected=%s identity=%s",
                caller_email,
                expected_sa,
                identity_name,
            )
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"unauthorized service account caller for {identity_name}"
            )
        return {"email": caller_email}

    if settings.planproof_env == "production":
        try:
            req = google_requests.Request()
            token_claims = id_token.verify_oauth2_token(
                token_str, req, audience=worker_audience
            )
            email = token_claims.get("email")
            if not email or (expected_sa and email.lower() != expected_sa.lower()):
                logger.warning(
                    "internal_task_forbidden caller=%s expected=%s identity=%s",
                    email,
                    expected_sa,
                    identity_name,
                )
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN, f"unauthorized service account caller for {identity_name}"
                )
            return token_claims
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("internal_task_auth_failed identity=%s error=%s", identity_name, exc)
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, f"invalid OIDC token for {identity_name}"
            ) from exc

    return {"caller": "internal-dev-test"}


async def verify_tasks_invoker_auth(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Verify Google Cloud Tasks OIDC token specifically bound to the Tasks Invoker service account."""
    worker_audience = str(settings.planproof_worker_service_url).rstrip("/") if settings.planproof_worker_service_url else "https://planproof-worker"
    return await _verify_oidc_token(
        authorization,
        settings.planproof_tasks_invoker_service_account,
        settings,
        worker_audience,
        "tasks-invoker",
    )


async def verify_scheduler_invoker_auth(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Verify Google Cloud Scheduler OIDC token specifically bound to the Scheduler Invoker service account."""
    worker_audience = str(settings.planproof_worker_service_url).rstrip("/") if settings.planproof_worker_service_url else "https://planproof-worker"
    expected_sa = (
        settings.planproof_scheduler_invoker_service_account
        or settings.planproof_tasks_invoker_service_account
    )
    return await _verify_oidc_token(
        authorization,
        expected_sa,
        settings,
        worker_audience,
        "scheduler-invoker",
    )


class TaskPayload(BaseModel):
    run_id: str | None = None
    execution_generation: int | None = None


async def _execution_claim_heartbeat(
    database: Any,
    run_id: str,
    generation: int,
    claim_id: str,
    stop_event: asyncio.Event,
    interval_seconds: int = 30,
) -> None:
    """Periodically renew the execution claim lease while the worker is actively running."""
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            break
        except TimeoutError:
            pass

        now = datetime.now(UTC)
        lease_expires = now + timedelta(seconds=120)
        res = await database.verification_runs.update_one(
            {
                "id": run_id,
                "execution_generation": generation,
                "execution_claim_id": claim_id,
            },
            {
                "$set": {
                    "execution_lease_expires_at": lease_expires,
                    "updated_at": now,
                }
            },
        )
        if res.matched_count == 0:
            logger.warning(
                "execution_claim_heartbeat_lost_ownership run_id=%s gen=%s claim=%s",
                run_id,
                generation,
                claim_id,
            )
            break


@router.post("/verification/{run_id}", status_code=status.HTTP_200_OK)
async def execute_verification_task(
    run_id: str,
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    _caller: Annotated[dict, Depends(verify_tasks_invoker_auth)],
    payload: TaskPayload | None = None,
) -> dict[str, Any]:
    """Execute a verification run invoked by Google Cloud Tasks.
    
    Reloads all canonical state from MongoDB. Uses atomic state & lease fencing so duplicate
    or stale generation deliveries do not cause duplicate workflow executions. Returns
    retryable HTTP 503 if another execution claim is currently active and unexpired.
    """
    database = mongo.database()
    quota_service = QuotaService(database, settings)
    runs_repo = RunRepository(mongo)
    verification_repo = VerificationRepository(mongo)

    # 1. Reload canonical run document from MongoDB
    run_doc = await database.verification_runs.find_one({"id": run_id})
    if not run_doc:
        logger.warning("execute_verification_task_not_found run_id=%s", run_id)
        return {"status": "not_found", "run_id": run_id}

    current_gen = run_doc.get("execution_generation", 0)
    task_gen = payload.execution_generation if (payload and payload.execution_generation is not None) else 0

    # Stale generation check: if task generation is older than canonical run generation, ignore safely with 200
    if task_gen < current_gen:
        logger.info(
            "run_stale_task_generation_ignored run_id=%s task_gen=%s current_gen=%s",
            run_id,
            task_gen,
            current_gen,
        )
        return {
            "status": "skipped_stale_generation",
            "run_id": run_id,
            "task_gen": task_gen,
            "current_gen": current_gen,
        }

    run_status = run_doc.get("status")

    # 2. Check terminal status to avoid duplicate execution (Acknowledge HTTP 200)
    if run_status in TERMINAL_STATES:
        logger.info(
            "run_terminal_task_delivery_acknowledged run_id=%s status=%s",
            run_id,
            run_status,
        )
        return {"status": "skipped_already_terminal", "run_id": run_id, "status_value": run_status}

    # 3. Check suspended status (HUMAN_WAIT) (Acknowledge HTTP 200 - wait for human resume)
    if run_status in SUSPENDED_STATES:
        logger.info(
            "run_suspended_human_wait_acknowledged run_id=%s status=%s",
            run_id,
            run_status,
        )
        return {"status": "skipped_suspended_human_wait", "run_id": run_id, "status_value": run_status}

    # 4. Atomic execution claim with lease fencing
    now = datetime.now(UTC)
    claim_id = str(uuid4())
    lease_expires = now + timedelta(seconds=120)

    # Claim query allows:
    # A. Clean RUNNABLE_INITIAL_STATES (QUEUED, CREATED) matching current generation
    # B. Stale RECOVERABLE_EXECUTION_STATES (EXTRACTING_OBLIGATIONS, VERIFYING, FINALIZING) whose execution lease expired
    claim_query = {
        "id": run_id,
        "execution_generation": current_gen,
        "$or": [
            {"status": {"$in": list(RUNNABLE_INITIAL_STATES)}},
            {
                "status": {"$in": list(RECOVERABLE_EXECUTION_STATES)},
                "execution_lease_expires_at": {"$lt": now},
            },
        ],
    }
    claim_update = {
        "$set": {
            "status": VerificationRunStatus.EXTRACTING_OBLIGATIONS.value,
            "execution_claim_id": claim_id,
            "execution_claimed_at": now,
            "execution_lease_expires_at": lease_expires,
            "started_at": now,
            "updated_at": now,
        }
    }
    claimed = await database.verification_runs.find_one_and_update(claim_query, claim_update)
    if not claimed:
        # Check if an active live worker currently holds a valid unexpired lease
        active_lease_expires = run_doc.get("execution_lease_expires_at")
        if active_lease_expires:
            if active_lease_expires.tzinfo is None:
                active_lease_expires = active_lease_expires.replace(tzinfo=UTC)
            if active_lease_expires >= now:
                logger.info("run_active_lease_held_by_live_worker run_id=%s", run_id)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="execution claim is currently active and unexpired",
                    headers={"Retry-After": "15"},
                )
        # If another worker just claimed or state is transient, return retryable HTTP 503 so Cloud Tasks retries
        logger.info("run_could_not_claim_execution_retrying run_id=%s", run_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="execution claim not acquired, retrying",
            headers={"Retry-After": "15"},
        )

    # 5. Acquire / refresh active execution lease slot
    project = await database.projects.find_one({"id": run_doc.get("project_id")})
    account_login = project.get("owner_id") if project else "system"
    try:
        await quota_service.acquire_active_run_reservation(
            account_login, run_doc.get("project_id", ""), run_id, lease_owner=claim_id
        )
    except Exception as exc:
        logger.warning("could_not_acquire_slot_on_worker run_id=%s error=%s", run_id, exc)

    # 6. Start periodic execution-claim heartbeat
    stop_heartbeat = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        _execution_claim_heartbeat(database, run_id, current_gen, claim_id, stop_heartbeat)
    )

    # 7. Execute bounded VerificationWorkflow
    try:
        await VerificationWorkflow(runs_repo, verification_repo, settings).run(run_id)
        return {"status": "completed", "run_id": run_id}
    except Exception as exc:
        logger.exception("verification_workflow_execution_failed run_id=%s", run_id, exc_info=exc)
        await database.verification_runs.update_one(
            {"id": run_id, "execution_claim_id": claim_id},
            {
                "$set": {
                    "status": VerificationRunStatus.FAILED.value,
                    "updated_at": datetime.now(UTC),
                    "execution_lease_expires_at": None,
                }
            },
        )
        return {"status": "failed", "run_id": run_id, "error": str(exc)}
    finally:
        # 8. Stop heartbeat and release active compute reservation matching this claim
        stop_heartbeat.set()
        try:
            await heartbeat_task
        except Exception:
            pass
        try:
            await quota_service.release_active_reservation(run_id, lease_owner=claim_id)
        except Exception:
            pass


@router.post("/recover-dispatches", response_model=TaskRecoveryResponse)
async def recover_pending_dispatches(
    mongo: Annotated[MongoManager, Depends(get_mongo)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    _caller: Annotated[dict, Depends(verify_scheduler_invoker_auth)],
) -> TaskRecoveryResponse:
    """Scan and recover stale PENDING, DISPATCH_FAILED, or stale DISPATCHING runs by retrying Cloud Task dispatch."""
    from app.api.workflow import dispatch_verification_run

    database = mongo.database()

    # Bounded query: find up to 20 stale un-dispatched runs
    now = datetime.now(UTC)
    stale_threshold = now - timedelta(seconds=30)
    stale_dispatching_threshold = now - timedelta(seconds=60)
    cursor = database.verification_runs.find(
        {
            "$or": [
                {
                    "enqueue_state": {"$in": ["PENDING", "DISPATCH_FAILED"]},
                    "created_at": {"$lt": stale_threshold},
                },
                {
                    "enqueue_state": "DISPATCHING",
                    "$or": [
                        {"dispatch_claimed_at": {"$lt": stale_dispatching_threshold}},
                        {"dispatch_claimed_at": None},
                    ],
                },
            ]
        }
    ).limit(20)

    stale_runs = [item async for item in cursor]
    dispatched_count = 0
    failed_count = 0

    for run in stale_runs:
        run_id = run["id"]
        success = await dispatch_verification_run(run_id, database, settings)
        if success:
            dispatched_count += 1
        else:
            failed_count += 1

    return TaskRecoveryResponse(
        scanned=len(stale_runs),
        dispatched=dispatched_count,
        failed=failed_count,
    )
