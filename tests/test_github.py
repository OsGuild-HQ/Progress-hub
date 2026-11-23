import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from progress_bot.github import API, GitHubClient, GitHubError

START, END = date(2026, 11, 23), date(2026, 11, 29)


def item(number: int, repo: str = "fedimint/fedimint") -> dict[str, object]:
    return {
        "html_url": f"https://github.com/{repo}/pull/{number}",
        "repository_url": f"https://api.github.com/repos/{repo}",
        "number": number,
        "title": f"PR {number}",
    }


def client(
    handler, tmp_path: Path | None = None, sleeps: list[float] | None = None
) -> GitHubClient:
    http = httpx.Client(base_url=API, transport=httpx.MockTransport(handler))
    return GitHubClient(
        "tok",
        http=http,
        cache_dir=tmp_path,
        sleep=(sleeps.append if sleeps is not None else lambda s: None),
        today=date(2026, 11, 30),
    )


def test_activity_queries_and_parsing(tmp_path: Path) -> None:
    queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer tok"
        q = request.url.params["q"]
        queries.append(q)
        if "merged:" in q:
            return httpx.Response(200, json={"items": [item(2)]})
        if "reviewed-by:" in q:
            return httpx.Response(200, json={"items": [item(9, "other/repo")]})
        return httpx.Response(200, json={"items": [item(1), item(2)]})

    gh = client(handler, tmp_path)
    activity = gh.activity("alice", START, END)
    assert [p.number for p in activity.opened] == [1, 2]
    assert [p.ref for p in activity.merged] == ["fedimint/fedimint#2"]
    assert [p.ref for p in activity.reviewed] == ["other/repo#9"]
    assert queries == [
        "type:pr author:alice created:2026-11-23..2026-11-29",
        "type:pr author:alice merged:2026-11-23..2026-11-29",
        "type:pr reviewed-by:alice -author:alice updated:2026-11-23..2026-11-29",
    ]

    # A finished week is cached: no more requests.
    again = gh.activity("alice", START, END)
    assert again == activity
    assert len(queries) == 3
    cached = json.loads((tmp_path / "alice_2026-11-23_2026-11-29.json").read_text())
    assert cached["opened"][0]["number"] == 1


def test_current_week_is_not_cached(tmp_path: Path) -> None:
    gh = client(lambda r: httpx.Response(200, json={"items": []}), tmp_path)
    gh.activity("alice", date(2026, 11, 30), date(2026, 12, 6))
    assert list(tmp_path.iterdir()) == []


def test_rate_limit_waits_then_retries() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(403, headers={"retry-after": "12"})
        return httpx.Response(200, json={"items": []})

    sleeps: list[float] = []
    client(handler, sleeps=sleeps).activity("alice", START, END)
    assert sleeps == [12.0]


def test_permission_error_and_unknown_user() -> None:
    with pytest.raises(GitHubError, match="refused"):
        client(lambda r: httpx.Response(403, json={})).activity("alice", START, END)
    activity = client(lambda r: httpx.Response(422, json={})).activity("ghost", START, END)
    assert activity.empty
