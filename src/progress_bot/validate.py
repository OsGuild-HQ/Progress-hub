"""Rules a contributor folder must follow, checked on every pull request."""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from pathlib import Path

from progress_bot.models import WEEK_SECTIONS, Contributor, Issue
from progress_bot.parser import load_roster
from progress_bot.weeks import monday_of, month_label, parse_month

LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")


def check_contributor(c: Contributor, today: date) -> list[Issue]:
    issues: list[Issue] = []
    p = c.profile
    if not LOGIN_RE.match(p.github):
        issues.append(Issue(p.path, 1, f"'{p.github}' is not a valid GitHub username"))
    if p.github.lower() != c.folder.name.lower():
        issues.append(
            Issue(
                p.path,
                1,
                f"folder is '{c.folder.name}' but github is '{p.github}'; they must match",
            )
        )
    if p.mentor and p.mentor.lower() == p.github.lower():
        issues.append(Issue(p.path, 1, "a contributor cannot be their own mentor"))
    if p.level in ("spartan", "adventurer") and not p.mentor:
        issues.append(Issue(p.path, 1, "no mentor assigned yet", "warning"))

    this_monday = monday_of(today)
    for m in c.months:
        try:
            parse_month(m.month)
        except ValueError:
            issues.append(Issue(m.path, 1, f"'{m.path.name}' is not a real month"))
            continue
        if m.title_month and m.title_month != m.month:
            issues.append(
                Issue(m.path, 1, f"title says {m.title_month} but the file is {m.path.name}")
            )

        ids = Counter(o.id for o in m.objectives)
        for o in m.objectives:
            if ids[o.id] > 1:
                issues.append(Issue(m.path, o.line, f"objective ID {o.id} is used more than once"))
            if not o.text:
                issues.append(Issue(m.path, o.line, f"objective {o.id} has no description"))
        if not m.objectives:
            issues.append(Issue(m.path, 1, "no objectives planned for this month", "warning"))

        seen: set[date] = set()
        known_ids = set(ids)
        for w in m.weeks:
            if w.monday in seen:
                issues.append(Issue(m.path, w.line, f"week of {w.monday} appears twice"))
            seen.add(w.monday)
            if w.monday.weekday() != 0:
                fix = monday_of(w.monday)
                issues.append(
                    Issue(
                        m.path,
                        w.line,
                        f"{w.monday} is a {w.monday:%A}; use that week's Monday ({fix})",
                    )
                )
            elif month_label(w.monday) != m.month:
                issues.append(
                    Issue(
                        m.path,
                        w.line,
                        f"week of {w.monday} belongs in {month_label(w.monday)}.md",
                    )
                )
            if w.monday > this_monday:
                issues.append(Issue(m.path, w.line, f"week of {w.monday} is in the future"))

            for name in WEEK_SECTIONS:
                if name not in w.sections:
                    issues.append(
                        Issue(m.path, w.line, f"week of {w.monday} is missing '### {name}'")
                    )
                elif not w.sections[name]:
                    issues.append(
                        Issue(
                            m.path,
                            w.section_lines[name],
                            f"'### {name}' is empty; write 'None' if there is nothing to report",
                        )
                    )
            for name, line in w.section_lines.items():
                if name not in WEEK_SECTIONS:
                    issues.append(
                        Issue(m.path, line, f"unknown section '### {name}' is ignored", "warning")
                    )
            for ev in w.evidence:
                for tag in ev.objectives:
                    if tag not in known_ids:
                        issues.append(
                            Issue(
                                m.path,
                                w.line,
                                f"{ev.url} is tagged [{tag}] but there is no objective {tag}",
                                "warning",
                            )
                        )
    return issues


def check_roster(roster: list[Contributor], today: date) -> list[Issue]:
    issues: list[Issue] = []
    by_login = {c.login.lower(): c for c in roster}
    counts = Counter(c.login.lower() for c in roster)
    for c in roster:
        issues.extend(check_contributor(c, today))
        if counts[c.login.lower()] > 1:
            issues.append(Issue(c.profile.path, 1, f"@{c.login} has more than one folder"))
        mentor = c.profile.mentor
        if mentor and mentor.lower() != c.login.lower():
            found = by_login.get(mentor.lower())
            if found is None:
                issues.append(
                    Issue(c.profile.path, 1, f"mentor @{mentor} has no profile here", "warning")
                )
            elif found.profile.level != "sentinel":
                issues.append(
                    Issue(c.profile.path, 1, f"mentor @{mentor} is not a Sentinel", "warning")
                )
    return issues


def validate(root: Path, today: date | None = None) -> list[Issue]:
    roster, issues = load_roster(root)
    issues.extend(check_roster(roster, today or date.today()))
    return sorted(issues, key=lambda i: (str(i.path), i.line))
