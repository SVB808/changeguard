import base64

import pytest

from changeguard.github_client import GitHubAPIError, GitHubClient


def test_rejects_invalid_repository_name():
    client = GitHubClient()

    with pytest.raises(GitHubAPIError):
        client.get_pull_request("https://example.com/not-a-repo", 1)


def test_rejects_non_positive_pr_number():
    client = GitHubClient()

    with pytest.raises(GitHubAPIError):
        client.get_pull_request("acme/orders", 0)


def test_fetches_text_file_at_exact_ref():
    class FakeContentClient(GitHubClient):
        def _get_json(self, path: str):
            assert path == (
                "/repos/acme/orders/contents/src/main/java/Order.java?ref="
                + "a" * 40
            )
            return {
                "type": "file",
                "encoding": "base64",
                "content": base64.b64encode(b"class Order {}\n").decode("ascii"),
            }

    result = FakeContentClient().get_file_text(
        "acme/orders",
        "src/main/java/Order.java",
        "a" * 40,
    )

    assert result == "class Order {}\n"


def test_missing_file_at_ref_returns_none():
    class MissingContentClient(GitHubClient):
        def _get_json(self, path: str):
            raise GitHubAPIError(
                "GitHub API returned HTTP 404: Not Found",
                status_code=404,
            )

    result = MissingContentClient().get_file_text(
        "acme/orders",
        "src/main/java/Missing.java",
        "b" * 40,
    )

    assert result is None


def test_lists_only_blob_paths_from_repository_tree():
    class FakeTreeClient(GitHubClient):
        def _get_json(self, path: str):
            assert path == "/repos/acme/orders/git/trees/main?recursive=1"
            return {
                "truncated": False,
                "tree": [
                    {"path": "pom.xml", "type": "blob"},
                    {"path": "src", "type": "tree"},
                    {"path": "src/main/App.java", "type": "blob"},
                ],
            }

    assert FakeTreeClient().list_repository_paths("acme/orders", "main") == [
        "pom.xml",
        "src/main/App.java",
    ]


def test_rejects_truncated_repository_tree():
    class TruncatedTreeClient(GitHubClient):
        def _get_json(self, path: str):
            return {"truncated": True, "tree": []}

    with pytest.raises(GitHubAPIError, match="truncated"):
        TruncatedTreeClient().list_repository_paths("acme/orders", "main")


def test_rate_limit_error_exposes_status_and_hint_signal():
    error = GitHubAPIError(
        "GitHub API returned HTTP 403: API rate limit exceeded",
        status_code=403,
    )

    assert error.status_code == 403
    assert error.is_rate_limited is True


def test_unrelated_forbidden_error_is_not_classified_as_rate_limit():
    error = GitHubAPIError(
        "GitHub API returned HTTP 403: Resource not accessible",
        status_code=403,
    )

    assert error.is_rate_limited is False
