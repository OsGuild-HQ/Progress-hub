"""PRs opened, PRs merged and reviews, from the GitHub search API.

Search allows 30 requests a minute with a token (10 without), so the client
waits out the rate limit instead of failing, and caches finished periods.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from progress_bot.models import Activity, PullRequest

API = "https://api.github.com"
MAX_WAIT = 90.0  # seconds; longer rate-limit waits give up


class GitHubError(Exception):
    pass


def _repo_from(item: dict[str, Any]) -> str:
    url = str(item.get("repository_url", ""))
    return "/".join(url.rstrip("/").split("/")[-2:])


def _to_pr(item: dict[str, Any]) -> PullRequest:
    return PullRequest(
        url=str(item["html_url"]),
        repo=_repo_from(item),
        number=int(item["number"]),
        title=str(item.get("title", "")),
    )


class GitHubClient:
    def __init__(
        self,
        token: str | None,
        *,
        http: httpx.Client | None = None,
        cache_dir: Path | None = None,
        sleep: Callable[[float], None] = time.sleep,
        today: date | None = None,
    ) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "osguild-progress-bot",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.http = http or httpx.Client(base_url=API, timeout=30.0)
        self.http.headers.update(headers)
        self.cache_dir = cache_dir
        self.sleep = sleep
        self.today = today or date.today()

    def _get(self, params: dict[str, str | int]) -> dict[str, Any]:
        for _ in range(4):
            try:
                resp = self.http.get("/search/issues", params=params)
            except httpx.HTTPError as exc:
                raise GitHubError(f"could not reach GitHub: {exc}") from exc
            if resp.status_code in (403, 429):
                wait = self._rate_limit_wait(resp)
                if wait is None:
                    raise GitHubError(f"GitHub refused the request ({resp.status_code})")
                print(f"GitHub rate limit hit; waiting {wait:.0f}s", file=sys.stderr)
                self.sleep(wait)
                continue
            if resp.status_code == 422:
                # Unknown user: search rejects the query. Treat as no activity.
                return {"items": []}
            if resp.status_code != 200:
                raise GitHubError(f"GitHub search failed ({resp.status_code}): {resp.text[:200]}")
            return resp.json()
        raise GitHubError("GitHub rate limit did not clear")

    @staticmethod
    def _rate_limit_wait(resp: httpx.Response) -> float | None:
        retry_after = resp.headers.get("retry-after")
        if retry_after and retry_after.isdigit():
            wait = float(retry_after)
        elif resp.headers.get("x-ratelimit-remaining") == "0":
            reset = float(resp.headers.get("x-ratelimit-reset", "0"))
            wait = max(reset - time.time(), 0) + 1
        else:
            return None  # a real permission error
        return wait if wait <= MAX_WAIT else None

    def _search(self, query: str) -> list[PullRequest]:
        data = self._get({"q": query, "per_page": 100, "sort": "created", "order": "asc"})
        return [_to_pr(item) for item in data.get("items", [])]

    def activity(self, login: str, start: date, end: date) -> Activity:
        """PR activity for `login` between `start` and `end`, both inclusive."""
        cache = self._cache_path(login, start, end)
        if cache is not None and cache.is_file():
            return _activity_from_json(json.loads(cache.read_text(encoding="utf-8")))

        span = f"{start.isoformat()}..{end.isoformat()}"
        activity = Activity(
            opened=self._search(f"type:pr author:{login} created:{span}"),
            merged=self._search(f"type:pr author:{login} merged:{span}"),
            # Approximate: PRs by others that this user reviewed and that changed in the period.
            reviewed=self._search(f"type:pr reviewed-by:{login} -author:{login} updated:{span}"),
        )
        if cache is not None and end < self.today:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(_activity_to_json(activity)), encoding="utf-8")
        return activity

    def _cache_path(self, login: str, start: date, end: date) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"{login.lower()}_{start}_{end}.json"


def _activity_to_json(a: Activity) -> dict[str, list[dict[str, Any]]]:
    def dump(prs: list[PullRequest]) -> list[dict[str, Any]]:
        return [{"url": p.url, "repo": p.repo, "number": p.number, "title": p.title} for p in prs]

    return {"opened": dump(a.opened), "merged": dump(a.merged), "reviewed": dump(a.reviewed)}


def _activity_from_json(data: dict[str, list[dict[str, Any]]]) -> Activity:
    def load(key: str) -> list[PullRequest]:
        return [PullRequest(**item) for item in data.get(key, [])]

    return Activity(opened=load("opened"), merged=load("merged"), reviewed=load("reviewed"))
