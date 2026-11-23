"""Turn parsed files and GitHub activity into per-contributor status and flags.

Flags exist to point mentors at people who may need help early. They are
not scores.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from progress_bot.models import Activity, Contributor, Objective, PullRequest, WeekEntry
from progress_bot.weeks import Week

MISSING = "missing report"
BLOCKED = "blocked"
REPEATED_BLOCKER = "blocked 3 weeks running"
SUPPORT = "asked for support"
QUIET = "quiet"
NO_PLAN = "no plan this month"

STREAK_LOOKBACK = 8


@dataclass
class ContributorWeek:
    contributor: Contributor
    week: Week
    expected: bool  # inactive or not-yet-joined contributors are not expected to report
    entry: WeekEntry | None
    objectives: list[Objective]
    activity: Activity | None = None
    github_error: str | None = None
    missing_streak: int = 0
    flags: list[str] = field(default_factory=list)
    unreported: list[PullRequest] = field(default_factory=list)
    narrative: str | None = None

    @property
    def login(self) -> str:
        return self.contributor.login

    @property
    def objectives_done(self) -> int:
        return sum(o.done for o in self.objectives)

    def evidence_for(self, objective_id: str) -> int:
        if self.entry is None:
            return 0
        return sum(objective_id in ev.objectives for ev in self.entry.evidence)


def is_expected(c: Contributor, week: Week) -> bool:
    """Active contributors are expected to report from their first month file on."""
    first = c.first_month
    return c.profile.active and first is not None and week.month >= first


def missing_streak(c: Contributor, week: Week) -> int:
    streak = 0
    for back in range(STREAK_LOOKBACK):
        w = week.previous(back)
        if not is_expected(c, w) or c.week(w.monday) is not None:
            break
        streak += 1
    return streak


def has_blockers(c: Contributor, week: Week) -> bool:
    entry = c.week(week.monday)
    return entry is not None and bool(entry.blockers)


def analyse(
    c: Contributor,
    week: Week,
    fetch: Callable[[Contributor, Week], Activity] | None = None,
) -> ContributorWeek:
    month = c.month(week.month)
    cw = ContributorWeek(
        contributor=c,
        week=week,
        expected=is_expected(c, week),
        entry=c.week(week.monday),
        objectives=month.objectives if month else [],
    )
    if fetch is not None:
        try:
            cw.activity = fetch(c, week)
        except Exception as exc:  # one bad lookup must not sink the whole report
            cw.github_error = str(exc)

    if not cw.expected:
        return cw

    cw.missing_streak = missing_streak(c, week)
    if month is None:
        cw.flags.append(NO_PLAN)
    if cw.entry is None:
        cw.flags.append(MISSING)
        no_activity = cw.activity is not None and cw.activity.empty
        if cw.missing_streak >= 2 and no_activity:
            cw.flags.append(QUIET)
    else:
        if cw.entry.blockers:
            if all(has_blockers(c, week.previous(n)) for n in (1, 2)):
                cw.flags.append(REPEATED_BLOCKER)
            else:
                cw.flags.append(BLOCKED)
        if cw.entry.support_needed:
            cw.flags.append(SUPPORT)

    if cw.activity is not None:
        reported = {ev.key for ev in cw.entry.evidence} if cw.entry else set()
        seen: set[str] = set()
        for pr in (*cw.activity.opened, *cw.activity.merged):
            if pr.key not in reported and pr.key not in seen:
                seen.add(pr.key)
                cw.unreported.append(pr)
    return cw


# Flags that put someone on a mentor's "needs attention" list.
ATTENTION = (MISSING, QUIET, REPEATED_BLOCKER, BLOCKED, SUPPORT, NO_PLAN)


def needs_attention(cw: ContributorWeek) -> bool:
    return any(flag in ATTENTION for flag in cw.flags)
