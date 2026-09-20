from __future__ import annotations

from pymongo.errors import DuplicateKeyError

from app.core.errors import DuplicateResourceError
from app.db.mongo import MongoManager
from app.domain.projects import Project


class ProjectsRepository:
    def __init__(self, mongo: MongoManager) -> None:
        self._mongo = mongo

    async def create(self, project: Project) -> Project:
        try:
            await self._mongo.database().projects.insert_one(project.model_dump(mode="json"))
        except DuplicateKeyError as exc:
            raise DuplicateResourceError(f"Project {project.id} already exists") from exc
        return project

    async def get(self, project_id: str) -> Project | None:
        document = await self._mongo.database().projects.find_one({"id": project_id})
        return Project.model_validate(document) if document else None
