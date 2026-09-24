from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from google.api_core.exceptions import AlreadyExists, GoogleAPIError
from google.cloud import tasks_v2
from google.protobuf import duration_pb2

from app.core.config import Settings

logger = logging.getLogger(__name__)


class CloudTasksDispatcher:
    """Dispatches verification runs to Google Cloud Tasks for scale-to-zero worker execution."""

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self.settings = settings
        self._client = client

    def _get_client(self) -> tasks_v2.CloudTasksClient | None:
        if self._client is not None:
            return self._client
        try:
            self._client = tasks_v2.CloudTasksClient()
            return self._client
        except Exception as exc:
            logger.error("Failed to initialize Google CloudTasksClient: %s", exc)
            return None

    def _format_task_id(self, run_id: str, execution_generation: int = 0) -> str:
        """Deterministic, safe Cloud Task ID derived from run_id and execution_generation."""
        clean_id = run_id.replace("_", "-").replace(":", "-").lower()
        gen_suffix = f"-g{execution_generation}"
        max_base = 60 - len(gen_suffix)
        if len(clean_id) <= max_base:
            return f"run-{clean_id}{gen_suffix}"
        h = hashlib.sha256(run_id.encode()).hexdigest()[:16]
        return f"run-{clean_id[:35]}-{h}{gen_suffix}"

    def build_task_name(self, run_id: str, execution_generation: int = 0) -> str:
        """Return the fully-qualified Cloud Task resource name."""
        project = self.settings.planproof_gcp_project_id
        location = self.settings.planproof_cloud_tasks_location
        queue = self.settings.planproof_cloud_tasks_queue
        task_id = self._format_task_id(run_id, execution_generation)
        return f"projects/{project}/locations/{location}/queues/{queue}/tasks/{task_id}"

    async def dispatch_run(self, run_id: str, execution_generation: int = 0) -> bool:
        """Create a Cloud Task for a verification run.
        
        Returns True on successful task creation or if task already exists (idempotent).
        Returns False on failure without raising unhandled exceptions.
        """
        # 1. In production, fail closed if configuration is missing
        if self.settings.planproof_env == "production":
            if (
                not self.settings.planproof_gcp_project_id
                or not self.settings.planproof_worker_service_url
                or not self.settings.planproof_tasks_invoker_service_account
            ):
                logger.error("Cloud Tasks dispatch failed closed: missing required production configuration")
                return False

        # 2. In development or test with unconfigured GCP, allow local test double/mock execution
        if (
            self.settings.planproof_env in {"development", "test"}
            and not self.settings.planproof_gcp_project_id
        ):
            logger.info("Local development/test environment without GCP project; mock dispatching run %s (gen %s)", run_id, execution_generation)
            return True

        client = self._get_client()
        if client is None:
            logger.error("Cloud Tasks client unavailable for run %s", run_id)
            return False

        project = self.settings.planproof_gcp_project_id
        location = self.settings.planproof_cloud_tasks_location
        queue = self.settings.planproof_cloud_tasks_queue
        worker_base_url = str(self.settings.planproof_worker_service_url).rstrip("/")
        invoker_sa = self.settings.planproof_tasks_invoker_service_account

        parent = client.queue_path(project, location, queue)
        task_id = self._format_task_id(run_id, execution_generation)
        task_name = f"{parent}/tasks/{task_id}"
        target_url = f"{worker_base_url}/internal/tasks/verification/{run_id}"

        # Strictly contain ONLY the run_id and execution_generation in the payload
        payload = json.dumps({"run_id": run_id, "execution_generation": execution_generation}).encode("utf-8")

        task = {
            "name": task_name,
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": target_url,
                "headers": {"Content-Type": "application/json"},
                "body": payload,
                "oidc_token": {
                    "service_account_email": invoker_sa,
                    "audience": worker_base_url,
                },
            },
            "dispatch_deadline": duration_pb2.Duration(seconds=1800),
        }

        try:
            client.create_task(request={"parent": parent, "task": task})
            logger.info("Cloud Task created successfully for run %s (task_name=%s)", run_id, task_name)
            return True
        except AlreadyExists:
            logger.info("Cloud Task already exists for run %s (task_name=%s); treating as idempotent success", run_id, task_name)
            return True
        except GoogleAPIError as exc:
            logger.error("Google Cloud Tasks API error while creating task for run %s: %s", run_id, exc)
            return False
        except Exception as exc:
            logger.error("Unexpected error creating Cloud Task for run %s: %s", run_id, exc)
            return False
