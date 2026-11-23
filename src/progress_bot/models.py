"""Plain data parsed from contributor files and GitHub."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

Severity = Literal["error", "warning"]

LEVELS = ("sentinel", "spartan", "adventurer")

# H2 headings of a month file's plan, mapped to the short category name.
CATEGORIES = {
    "Technical Development": "technical",
    "Open-Source Contributions": "contributions",
    "Community Participation": "community",
}

# H3 headings every weekly entry must have, in template order.
WEEK_SECTIONS = (
    "Accomplished",
    "Repositories",
    "Issues & PRs",
    "Learned",
    "Blockers",
    "Support Needed",
    "Next Week",
)

# Bullet text that means "nothing to report".
_NOTHING = {"none", "n/a", "na", "nothing", "-", "no", "nil", "none."}


def is_nothing(text: str) -> bool:
    return text.strip().lower() in _NOTHING


@dataclass(frozen=True)
class Issue:
    path: Path
    line: int
    message: str
    severity: Severity = "error"


@dataclass
class Profile:
    path: Path
    name: str
    github: str
    level: str
    mentor: str | None = None
    languages: list[str] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)
    focus: str = ""
    active: bool = True


@dataclass
class Objective:
    id: str
    category: str
    text: str
    done: bool
    line: int


@dataclass(frozen=True)
class Evidence:
    """A GitHub issue or PR link in a weekly entry."""

    url: str
    repo: str  # owner/name
    kind: Literal["pull", "issues"]
    number: int
    objectives: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return f"{self.repo.lower()}#{self.number}"


@dataclass
class WeekEntry:
    monday: date
    line: int
    sections: dict[str, list[str]] = field(default_factory=dict)
    section_lines: dict[str, int] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)

    def items(self, section: str) -> list[str]:
        """Meaningful items of a section: placeholders like 'None' dropped."""
        return [item for item in self.sections.get(section, []) if not is_nothing(item)]

    @property
    def blockers(self) -> list[str]:
        return self.items("Blockers")

    @property
    def support_needed(self) -> list[str]:
        return self.items("Support Needed")


@dataclass
class MonthFile:
    path: Path
    month: str  # YYYY-MM, from the file name
    title_month: str | None = None  # YYYY-MM from the H1, if it parsed
    objectives: list[Objective] = field(default_factory=list)
    weeks: list[WeekEntry] = field(default_factory=list)


@dataclass
class Contributor:
    folder: Path
    profile: Profile
    months: list[MonthFile] = field(default_factory=list)

    @property
    def login(self) -> str:
        return self.profile.github

    def month(self, month: str) -> MonthFile | None:
        return next((m for m in self.months if m.month == month), None)

    def week(self, monday: date) -> WeekEntry | None:
        for m in self.months:
            for entry in m.weeks:
                if entry.monday == monday:
                    return entry
        return None

    @property
    def first_month(self) -> str | None:
        return min((m.month for m in self.months), default=None)


@dataclass(frozen=True)
class PullRequest:
    url: str
    repo: str
    number: int
    title: str

    @property
    def key(self) -> str:
        return f"{self.repo.lower()}#{self.number}"

    @property
    def ref(self) -> str:
        return f"{self.repo}#{self.number}"


@dataclass
class Activity:
    opened: list[PullRequest] = field(default_factory=list)
    merged: list[PullRequest] = field(default_factory=list)
    reviewed: list[PullRequest] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.opened or self.merged or self.reviewed)

    def keys(self) -> set[str]:
        return {pr.key for pr in (*self.opened, *self.merged, *self.reviewed)}
