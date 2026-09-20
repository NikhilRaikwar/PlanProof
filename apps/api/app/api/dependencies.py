from fastapi import Request

from app.db.mongo import MongoManager


def get_mongo(request: Request) -> MongoManager:
    return request.app.state.mongo
