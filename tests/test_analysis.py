from pathlib import Path

from progress_bot.analysis import (
    BLOCKED,
    MISSING,
    NO_PLAN,
    QUIET,
    REPEATED_BLOCKER,
    SUPPORT,
    analyse,
    needs_attention,
)
from progress_bot.models import Activity, Contributor, PullRequest
from progress_bot.parser import load_roster
from progress_bot.weeks import Week

W48 = Week.parse("2026-W48")


def roster(repo: Path) -> dict[str, Contributor]:
    contributors, _ = load_roster(repo)
    return {c.login: c for c in contributors}


def pr(number: int) -> PullRequest:
    return PullRequest(
        f"https://github.com/fedimint/fedimint/pull/{number}", "fedimint/fedimint", number, "t"
    )


def test_flags(repo: Path) -> None:
    people = roster(repo)
    alice = analyse(people["alice"], W48)
    assert alice.flags == [REPEATED_BLOCKER, SUPPORT]
    assert alice.objectives_done == 1
    assert alice.evidence_for("C1") == 1

    bob = analyse(people["bob"], W48)
    assert bob.flags == [MISSING]
    assert bob.missing_streak == 3  # W46, W47, W48; W45 had a report
    assert needs_attention(bob)

    sam = analyse(people["sam-sentinel"], W48)
    assert sam.flags == []
    assert not needs_attention(sam)

    carol = analyse(people["carol"], W48)
    assert not carol.expected
    assert carol.flags == []


def test_single_blocked_week(repo: Path) -> None:
    alice = analyse(roster(repo)["alice"], Week.parse("2026-W46"))
    assert alice.flags == [BLOCKED]


def test_not_expected_before_first_month(repo: Path) -> None:
    bob = analyse(roster(repo)["bob"], Week.parse("2026-W40"))
    assert not bob.expected
    assert bob.flags == []


def test_no_plan_for_month(repo: Path) -> None:
    bob = analyse(roster(repo)["bob"], Week.parse("2026-W50"))
    assert bob.flags[:2] == [NO_PLAN, MISSING]


def test_quiet_needs_no_github_activity(repo: Path) -> None:
    bob = roster(repo)["bob"]
    quiet = analyse(bob, W48, lambda c, w: Activity())
    assert QUIET in quiet.flags
    busy = analyse(bob, W48, lambda c, w: Activity(opened=[pr(1)]))
    assert QUIET not in busy.flags
    assert [p.number for p in busy.unreported] == [1]


def test_unreported_prs_skip_linked_ones(repo: Path) -> None:
    alice = roster(repo)["alice"]
    cw = analyse(alice, W48, lambda c, w: Activity(opened=[pr(7010), pr(7020)], merged=[pr(7020)]))
    assert [p.number for p in cw.unreported] == [7020]


def test_github_failure_is_contained(repo: Path) -> None:
    def boom(c: Contributor, w: Week) -> Activity:
        raise RuntimeError("down")

    cw = analyse(roster(repo)["alice"], W48, boom)
    assert cw.github_error == "down"
    assert cw.activity is None
