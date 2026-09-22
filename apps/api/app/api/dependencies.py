from typing import Any

from fastapi import Request

from app.core.config import Settings, get_settings
from app.db.mongo import MongoManager


def get_mongo(request: Request) -> MongoManager:
    return request.app.state.mongo


def get_settings_dep(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


def verify_tenant_project_access(project: dict | Any, session: dict | None) -> None:
    if not session:
        return
    proj_dict = project.model_dump() if hasattr(project, "model_dump") else project
    proj_inst_id = proj_dict.get("github_installation_id")
    if proj_inst_id is not None:
        if proj_inst_id != session.get("installation_id"):
            from fastapi import HTTPException, status

            raise HTTPException(status.HTTP_404_NOT_FOUND, "resource not found")
        return
    owner_id = proj_dict.get("owner_id")
    if owner_id and owner_id != session.get("account_login"):
        from fastapi import HTTPException, status

        raise HTTPException(status.HTTP_404_NOT_FOUND, "resource not found")
