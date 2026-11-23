"""Snapshot tests: run with UPDATE_GOLDEN=1 to rewrite the expected reports."""

import os
from datetime import date
from pathlib import Path

from conftest import FIXTURES
from progress_bot.analysis import analyse
from progress_bot.models import Activity, Contributor, PullRequest
from progress_bot.parser import load_roster
from progress_bot.summarize import ContributorMonth, ReportContext, monthly_report, weekly_report
from progress_bot.weeks import Week


def pr(number: int, repo: str = "fedimint/fedimint") -> PullRequest:
    return PullRequest(f"https://github.com/{repo}/pull/{number}", repo, number, f"PR {number}")


ACTIVITY = {
    "alice": Activity(opened=[pr(7010), pr(7011)], reviewed=[pr(55, "osguild/architect")]),
    "sam-sentinel": Activity(reviewed=[pr(7010)], merged=[pr(7001)]),
    "bob": Activity(),
}


def fake_fetch(c: Contributor, w: Week) -> Activity:
    if c.login == "carol":
        raise RuntimeError("should not matter")
    return ACTIVITY[c.login]


def check_golden(name: str, text: str) -> None:
    path = FIXTURES / name
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_text(text, encoding="utf-8")
    assert text == path.read_text(encoding="utf-8")


def test_weekly_report(repo: Path) -> None:
    roster, _ = load_roster(repo)
    week = Week.parse("2026-W48")
    results = [analyse(c, week, fake_fetch) for c in roster]
    next(r for r in results if r.login == "alice").narrative = "Alice opened a draft PR."
    ctx = ReportContext(generated=date(2026, 11, 30), github=True, llm=True)
    check_golden("weekly-2026-W48.md", weekly_report(results, week, ctx))


def test_weekly_report_without_github(repo: Path) -> None:
    roster, _ = load_roster(repo)
    week = Week.parse("2026-W48")
    text = weekly_report(
        [analyse(c, week) for c in roster],
        week,
        ReportContext(generated=date(2026, 11, 30), github=False, llm=False),
    )
    assert "| PRs opened / merged | – / – |" in text
    assert "AI-generated" not in text
    assert "- @bob: missing report (3 weeks)" in text


def test_monthly_report(repo: Path) -> None:
    roster, _ = load_roster(repo)
    results = [ContributorMonth(c, "2026-11", activity=ACTIVITY.get(c.login)) for c in roster]
    ctx = ReportContext(generated=date(2026, 12, 1), github=True, llm=False)
    check_golden("monthly-2026-11.md", monthly_report(results, "2026-11", ctx))
