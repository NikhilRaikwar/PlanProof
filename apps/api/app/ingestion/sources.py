from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from app.domain.projects import RepositorySourceType

_GITHUB_PATH = re.compile(r"^/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")


class InvalidRepositorySource(ValueError):
    pass


@dataclass(frozen=True)
class RepositorySource:
    source_type: RepositorySourceType
    identity: str
    requested_ref: str | None


@dataclass(frozen=True)
class PublicGitHubSource(RepositorySource):
    owner: str
    repository: str
    clone_url: str

    @classmethod
    def from_url(cls, repository_url: str, requested_ref: str | None = None) -> PublicGitHubSource:
        parsed = urlparse(repository_url)
        if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
            raise InvalidRepositorySource(
                "only canonical HTTPS GitHub repository URLs are supported"
            )
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise InvalidRepositorySource(
                "repository URL must not contain credentials, query, or fragment"
            )
        match = _GITHUB_PATH.fullmatch(parsed.path)
        if not match:
            raise InvalidRepositorySource(
                "repository URL must contain exactly an owner and repository"
            )
        owner, repository = match.groups()
        identity = f"github:{owner.lower()}/{repository.lower()}"
        return cls(
            source_type=RepositorySourceType.PUBLIC_GITHUB,
            identity=identity,
            requested_ref=requested_ref,
            owner=owner,
            repository=repository.removesuffix(".git"),
            clone_url=f"https://github.com/{owner}/{repository.removesuffix('.git')}.git",
        )


@dataclass(frozen=True)
class SeededFixtureSource(RepositorySource):
    fixture_id: str
    fixture_path: Path


def seeded_fixture_source(fixture_id: str, fixtures_root: Path) -> SeededFixtureSource:
    # Registry maps an explicit fixture identifier to a local test repository only; it contains no
    # expected evaluator outcomes and shares all downstream ingestion code with public repositories.
    registry = {"partial-refunds-v1": "payments-platform"}
    fixture_path = (fixtures_root / registry.get(fixture_id, "")).resolve()
    if not fixture_path.is_dir() or fixture_path.parent != fixtures_root.resolve():
        raise InvalidRepositorySource("unknown seeded fixture")
    return SeededFixtureSource(
        source_type=RepositorySourceType.SEEDED,
        identity=f"fixture:{fixture_id}",
        requested_ref="fixture",
        fixture_id=fixture_id,
        fixture_path=fixture_path,
    )
