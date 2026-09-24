from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.config import Settings
from app.domain.runs import VerificationRunStatus

logger = logging.getLogger(__name__)


class QuotaExhaustedError(HTTPException):
    def __init__(self, message: str, retry_after_seconds: int = 3600) -> None:
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=message,
            headers={"Retry-After": str(retry_after_seconds)},
        )


class QuotaService:
    def __init__(self, database: AsyncDatabase, settings: Settings) -> None:
        self.db = database
        self.settings = settings

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _daily_period_str(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%d")

    @staticmethod
    def _monthly_period_str(dt: datetime) -> str:
        return dt.strftime("%Y-%m-01")

    async def _consume_bucket(
        self,
        scope_type: str,
        scope_id: str,
        quota_type: str,
        period_start: str,
        limit: int,
        error_message: str,
        retry_after_seconds: int = 3600,
    ) -> dict[str, Any]:
        """Atomically increment a quota bucket if count < limit. Fails closed on DB error."""
        now = self._utc_now()
        query = {
            "scope_type": scope_type,
            "scope_id": str(scope_id),
            "quota_type": quota_type,
            "period_start": period_start,
        }

        try:
            # 1. Attempt conditional atomic increment if document already exists
            res = await self.db.account_quotas.find_one_and_update(
                {**query, "count": {"$lt": limit}},
                {"$inc": {"count": 1}, "$set": {"limit": limit, "updated_at": now}},
                return_document=True,
            )
            if res is not None:
                return res

            # 2. If not found, check if it exists and is at/above limit
            existing = await self.db.account_quotas.find_one(query)
            if existing is not None:
                if existing.get("count", 0) >= limit:
                    raise QuotaExhaustedError(error_message, retry_after_seconds)

            # 3. Document does not exist yet: attempt to insert first counter = 1
            doc = {
                **query,
                "count": 1,
                "limit": limit,
                "created_at": now,
                "updated_at": now,
            }
            try:
                await self.db.account_quotas.insert_one(doc)
                return doc
            except DuplicateKeyError:
                # Concurrent insert won race; retry atomic increment
                retry_res = await self.db.account_quotas.find_one_and_update(
                    {**query, "count": {"$lt": limit}},
                    {"$inc": {"count": 1}, "$set": {"limit": limit, "updated_at": now}},
                    return_document=True,
                )
                if retry_res is not None:
                    return retry_res
                raise QuotaExhaustedError(error_message, retry_after_seconds) from None

        except QuotaExhaustedError:
            raise
        except PyMongoError as exc:
            logger.error("quota_database_error query=%s error=%s", query, exc)
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "quota verification unavailable"
            ) from exc

    async def rollback_bucket(
        self, scope_type: str, scope_id: str, quota_type: str, period_start: str
    ) -> None:
        """Roll back a previously reserved quota count if run creation fails before enqueue."""
        try:
            await self.db.account_quotas.update_one(
                {
                    "scope_type": scope_type,
                    "scope_id": str(scope_id),
                    "quota_type": quota_type,
                    "period_start": period_start,
                    "count": {"$gt": 0},
                },
                {"$inc": {"count": -1}, "$set": {"updated_at": self._utc_now()}},
            )
        except Exception as exc:
            logger.warning("quota_rollback_failed error=%s", exc)

    async def reserve_verification_run_quota(
        self, account_id: str, account_login: str
    ) -> list[tuple[str, str, str, str]]:
        """Check and atomically reserve daily, monthly, and global run quotas. Returns reserved keys for rollback."""
        if not self.settings.planproof_verification_enabled:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "verification service is currently paused for maintenance",
            )

        now = self._utc_now()
        daily_period = self._daily_period_str(now)
        monthly_period = self._monthly_period_str(now)
        reserved: list[tuple[str, str, str, str]] = []

        try:
            # 1. Global Daily Quota
            k_global = ("GLOBAL", "global", "GLOBAL_RUN_DAILY", daily_period)
            await self._consume_bucket(
                *k_global,
                limit=self.settings.planproof_global_runs_per_day,
                error_message="Global daily verification run limit reached for this beta. Please try again tomorrow.",
                retry_after_seconds=86400,
            )
            reserved.append(k_global)

            # 2. Account Daily Quota
            k_daily = ("ACCOUNT", account_id, "RUN_DAILY", daily_period)
            await self._consume_bucket(
                *k_daily,
                limit=self.settings.planproof_free_runs_per_day,
                error_message=f"Daily run limit reached for account {account_login} (max {self.settings.planproof_free_runs_per_day}/day).",
                retry_after_seconds=86400,
            )
            reserved.append(k_daily)

            # 3. Account Monthly Quota
            k_monthly = ("ACCOUNT", account_id, "RUN_MONTHLY", monthly_period)
            await self._consume_bucket(
                *k_monthly,
                limit=self.settings.planproof_free_runs_per_month,
                error_message=f"Monthly run limit reached for account {account_login} (max {self.settings.planproof_free_runs_per_month}/month).",
                retry_after_seconds=86400 * 7,
            )
            reserved.append(k_monthly)

            return reserved

        except Exception:
            # Rollback any previously acquired buckets
            for key in reserved:
                await self.rollback_bucket(*key)
            raise

    async def _consume_bucket_in_session(
        self,
        session: Any,
        scope_type: str,
        scope_id: str,
        quota_type: str,
        period_start: str,
        limit: int,
        error_message: str,
        retry_after_seconds: int = 3600,
    ) -> dict[str, Any]:
        """Check and increment a quota bucket within an active client session transaction."""
        now = self._utc_now()
        query = {
            "scope_type": scope_type,
            "scope_id": str(scope_id),
            "quota_type": quota_type,
            "period_start": period_start,
        }
        existing = await self.db.account_quotas.find_one(query, session=session)
        if existing is not None:
            if existing.get("count", 0) >= limit:
                raise QuotaExhaustedError(error_message, retry_after_seconds)
            await self.db.account_quotas.update_one(
                query,
                {"$inc": {"count": 1}, "$set": {"limit": limit, "updated_at": now}},
                session=session,
            )
            return {**existing, "count": existing.get("count", 0) + 1}
        else:
            doc = {
                **query,
                "count": 1,
                "limit": limit,
                "created_at": now,
                "updated_at": now,
            }
            await self.db.account_quotas.insert_one(doc, session=session)
            return doc

    async def create_verification_run_transactional(
        self,
        account_id: str,
        account_login: str,
        run_doc: dict,
        client: Any | None = None,
    ) -> dict:
        """Atomically reserve multi-bucket quotas and insert verification_runs in a single transaction."""
        if not self.settings.planproof_verification_enabled:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "verification service is currently paused for maintenance",
            )

        now = self._utc_now()
        daily_period = self._daily_period_str(now)
        monthly_period = self._monthly_period_str(now)

        if client and hasattr(client, "start_session"):
            try:
                async with await client.start_session() as session:
                    async with session.start_transaction():
                        await self._consume_bucket_in_session(
                            session,
                            "GLOBAL",
                            "global",
                            "GLOBAL_RUN_DAILY",
                            daily_period,
                            limit=self.settings.planproof_global_runs_per_day,
                            error_message="Global daily verification run limit reached for this beta. Please try again tomorrow.",
                            retry_after_seconds=86400,
                        )
                        await self._consume_bucket_in_session(
                            session,
                            "ACCOUNT",
                            account_id,
                            "RUN_DAILY",
                            daily_period,
                            limit=self.settings.planproof_free_runs_per_day,
                            error_message=f"Daily run limit reached for account {account_login} (max {self.settings.planproof_free_runs_per_day}/day).",
                            retry_after_seconds=86400,
                        )
                        await self._consume_bucket_in_session(
                            session,
                            "ACCOUNT",
                            account_id,
                            "RUN_MONTHLY",
                            monthly_period,
                            limit=self.settings.planproof_free_runs_per_month,
                            error_message=f"Monthly run limit reached for account {account_login} (max {self.settings.planproof_free_runs_per_month}/month).",
                            retry_after_seconds=86400 * 7,
                        )
                        await self.db.verification_runs.insert_one(run_doc, session=session)
                        return run_doc
            except QuotaExhaustedError:
                raise
            except DuplicateKeyError:
                raise
            except Exception as exc:
                err_msg = str(exc).lower()
                if (
                    "transaction" not in err_msg
                    and "replica set" not in err_msg
                    and "session" not in err_msg
                ):
                    raise

        # Standalone / mock fallback with atomic reservation + immediate compensation
        reserved_keys = await self.reserve_verification_run_quota(account_id, account_login)
        try:
            await self.db.verification_runs.insert_one(run_doc)
            return run_doc
        except Exception:
            await self.rollback_verification_run_quota(reserved_keys)
            raise

    async def rollback_verification_run_quota(
        self, reserved_keys: list[tuple[str, str, str, str]]
    ) -> None:
        for key in reserved_keys:
            await self.rollback_bucket(*key)

    async def reserve_snapshot_quota(self, account_id: str, account_login: str) -> None:
        """Check and atomically reserve daily snapshot creation quota."""
        if not self.settings.planproof_ingestion_enabled:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "repository ingestion is currently paused for maintenance",
            )
        now = self._utc_now()
        daily_period = self._daily_period_str(now)
        await self._consume_bucket(
            "ACCOUNT",
            account_id,
            "SNAPSHOT_DAILY",
            daily_period,
            limit=self.settings.planproof_snapshots_per_day,
            error_message=f"Daily snapshot limit reached for account {account_login} (max {self.settings.planproof_snapshots_per_day}/day).",
            retry_after_seconds=86400,
        )

    async def reserve_project_quota(self, account_login: str) -> None:
        """Atomically reserve project creation quota for this account."""
        await self._consume_bucket(
            "ACCOUNT",
            account_login,
            "PROJECT_CREATIONS_TOTAL",
            "permanent",
            limit=self.settings.planproof_max_project_creations_per_account,
            error_message=f"maximum project creation limit reached for this account (max {self.settings.planproof_max_project_creations_per_account} projects)",
            retry_after_seconds=3600,
        )

    async def rollback_project_quota(self, account_login: str) -> None:
        """Roll back project count if project persistence fails."""
        await self.rollback_bucket("ACCOUNT", account_login, "PROJECT_CREATIONS_TOTAL", "permanent")

    async def _reconcile_stale_slot(self, slot_id: str) -> None:
        """Check if slot is held by a terminated or paused run/ingestion and release it."""
        slot = await self.db.active_reservations.find_one({"slot_id": slot_id})
        if not slot:
            return
        r_id = slot.get("resource_id")
        if not r_id:
            await self.db.active_reservations.delete_one({"slot_id": slot_id})
            return
        now = self._utc_now()
        expires_at = slot.get("expires_at")
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        is_expired = bool(expires_at and expires_at < now)
        terminal_statuses = {
            VerificationRunStatus.COMPLETE.value,
            VerificationRunStatus.BLOCKED.value,
            VerificationRunStatus.INCONCLUSIVE.value,
            VerificationRunStatus.FAILED.value,
            VerificationRunStatus.HUMAN_WAIT.value,  # HUMAN_WAIT releases compute slot
        }
        if slot.get("resource_type") == "RUN":
            run_doc = await self.db.verification_runs.find_one({"id": r_id})
            if run_doc:
                if run_doc.get("status") in terminal_statuses or is_expired:
                    await self.db.active_reservations.delete_one({"slot_id": slot_id})
            elif is_expired:
                await self.db.active_reservations.delete_one({"slot_id": slot_id})
        elif slot.get("resource_type") == "INGESTION":
            snap_doc = await self.db.repository_snapshots.find_one({"id": r_id})
            if snap_doc:
                if snap_doc.get("status") in {"READY", "FAILED"} or is_expired:
                    await self.db.active_reservations.delete_one({"slot_id": slot_id})
            elif is_expired:
                await self.db.active_reservations.delete_one({"slot_id": slot_id})

    async def acquire_active_run_reservation(
        self, account_login: str, project_id: str, run_id: str, lease_owner: str | None = None
    ) -> None:
        """Acquire active run concurrency reservation using atomic slot documents."""
        now = self._utc_now()
        expires_at = now + timedelta(hours=2)
        account_slot_id = f"RUN_ACCOUNT:{account_login}"
        project_slot_id = f"RUN_PROJECT:{project_id}"
        owner = lease_owner or run_id

        # 1. Reconcile stale slots if previous holding run reached terminal status
        await self._reconcile_stale_slot(account_slot_id)
        await self._reconcile_stale_slot(project_slot_id)

        # 2. Atomically acquire account slot
        account_doc = {
            "slot_id": account_slot_id,
            "resource_id": run_id,
            "account_login": account_login,
            "project_id": project_id,
            "resource_type": "RUN",
            "lease_owner": owner,
            "status": "ACTIVE",
            "created_at": now,
            "updated_at": now,
            "expires_at": expires_at,
        }
        try:
            await self.db.active_reservations.insert_one(account_doc)
        except DuplicateKeyError:
            existing = await self.db.active_reservations.find_one({"slot_id": account_slot_id})
            if existing and existing.get("lease_owner") == owner:
                # Same owner refreshing lease
                await self.db.active_reservations.update_one(
                    {"slot_id": account_slot_id, "lease_owner": owner},
                    {"$set": {"expires_at": expires_at, "updated_at": now}},
                )
            else:
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    f"active run limit reached for this account (max {self.settings.planproof_max_active_runs_per_account} concurrent active run)",
                ) from None

        # 3. Atomically acquire project slot
        project_doc = {
            "slot_id": project_slot_id,
            "resource_id": run_id,
            "account_login": account_login,
            "project_id": project_id,
            "resource_type": "RUN",
            "lease_owner": owner,
            "status": "ACTIVE",
            "created_at": now,
            "updated_at": now,
            "expires_at": expires_at,
        }
        try:
            await self.db.active_reservations.insert_one(project_doc)
        except DuplicateKeyError:
            existing = await self.db.active_reservations.find_one({"slot_id": project_slot_id})
            if existing and existing.get("lease_owner") == owner:
                await self.db.active_reservations.update_one(
                    {"slot_id": project_slot_id, "lease_owner": owner},
                    {"$set": {"expires_at": expires_at, "updated_at": now}},
                )
            else:
                # Rollback account slot
                await self.db.active_reservations.delete_one(
                    {"slot_id": account_slot_id, "lease_owner": owner}
                )
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    f"active run limit reached for this project (max {self.settings.planproof_max_active_runs_per_project} concurrent active run)",
                ) from None

    async def renew_active_reservation(
        self, account_login: str, project_id: str, run_id: str, lease_owner: str | None = None
    ) -> bool:
        """Renew active reservation lease for an actively executing run (strictly fenced by lease_owner)."""
        now = self._utc_now()
        expires_at = now + timedelta(hours=2)
        account_slot_id = f"RUN_ACCOUNT:{account_login}"
        project_slot_id = f"RUN_PROJECT:{project_id}"
        owner = lease_owner or run_id

        res_account = await self.db.active_reservations.update_one(
            {"slot_id": account_slot_id, "lease_owner": owner},
            {"$set": {"expires_at": expires_at, "updated_at": now}},
        )
        res_project = await self.db.active_reservations.update_one(
            {"slot_id": project_slot_id, "lease_owner": owner},
            {"$set": {"expires_at": expires_at, "updated_at": now}},
        )
        m_account = getattr(res_account, "matched_count", 0) if res_account is not None else 0
        m_project = getattr(res_project, "matched_count", 0) if res_project is not None else 0
        return bool(m_account > 0 or m_project > 0)

    async def release_active_reservation(
        self, resource_id: str, lease_owner: str | None = None
    ) -> None:
        """Release active compute reservation slots when a run finishes or pauses (strictly fenced by lease_owner)."""
        owner = lease_owner or resource_id
        try:
            await self.db.active_reservations.delete_many(
                {"$or": [{"lease_owner": owner}, {"resource_id": resource_id, "lease_owner": owner}]}
            )
        except Exception as exc:
            logger.warning("release_reservation_failed resource_id=%s error=%s", resource_id, exc)

    async def acquire_active_ingestion_reservation(
        self, account_login: str, snapshot_id: str
    ) -> None:
        """Acquire active ingestion reservation using atomic slot document."""
        now = self._utc_now()
        expires_at = now + timedelta(minutes=30)
        ingestion_slot_id = f"INGESTION_ACCOUNT:{account_login}"
        await self._reconcile_stale_slot(ingestion_slot_id)

        doc = {
            "slot_id": ingestion_slot_id,
            "resource_id": snapshot_id,
            "account_login": account_login,
            "resource_type": "INGESTION",
            "lease_owner": snapshot_id,
            "status": "ACTIVE",
            "created_at": now,
            "updated_at": now,
            "expires_at": expires_at,
        }
        try:
            await self.db.active_reservations.insert_one(doc)
        except DuplicateKeyError:
            existing = await self.db.active_reservations.find_one({"slot_id": ingestion_slot_id})
            if existing and existing.get("lease_owner") == snapshot_id:
                await self.db.active_reservations.update_one(
                    {"slot_id": ingestion_slot_id, "lease_owner": snapshot_id},
                    {"$set": {"expires_at": expires_at, "updated_at": now}},
                )
            else:
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    f"active ingestion limit reached for this account (max {self.settings.planproof_max_active_ingestions_per_account} concurrent ingestion)",
                ) from None
