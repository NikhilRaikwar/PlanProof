from fastapi import Request

from app.core.config import Settings, get_settings
from app.db.mongo import MongoManager


def get_mongo(request: Request) -> MongoManager:
    return request.app.state.mongo


def get_settings_dep(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()

