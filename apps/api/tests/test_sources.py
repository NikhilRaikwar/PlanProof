import pytest

from app.ingestion.sources import InvalidRepositorySource, PublicGitHubSource


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/encode/httpx",
        "file:///tmp/repo",
        "ssh://github.com/a/b",
        "git@github.com:a/b",
        "https://user:pass@github.com/a/b",
        "https://evilgithub.com/a/b",
        "https://github.com/a/../b",
        "C:\\repo",
        "https://github.com/a",
        "https://localhost/a/b",
    ],
)
def test_unsafe_repository_urls_are_rejected(url: str) -> None:
    with pytest.raises(InvalidRepositorySource):
        PublicGitHubSource.from_url(url)


def test_canonical_public_github_url_is_normalized() -> None:
    source = PublicGitHubSource.from_url("https://github.com/encode/httpx/")
    assert source.identity == "github:encode/httpx"
    assert source.clone_url == "https://github.com/encode/httpx.git"
