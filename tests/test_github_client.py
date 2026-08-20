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
