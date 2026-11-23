"""Read contributor folders into models, reporting what could not be understood.

The parser is lenient: it keeps whatever it can read and returns `Issue`s for
the rest. Semantic rules (dates on Mondays, required sections, ...) live in
`validate.py`.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from markdown_it import MarkdownIt
from markdown_it.token import Token

from progress_bot.models import (
    CATEGORIES,
    LEVELS,
    Contributor,
    Evidence,
    Issue,
    MonthFile,
    Objective,
    Profile,
    WeekEntry,
)

PROFILE_FILE = "profile.md"
MONTH_FILE_RE = re.compile(r"^\d{4}-\d{2}\.md$")

_PLAN_TITLE_RE = re.compile(r"^Plan\s*[—–-]+\s*(\d{4}-\d{2})$")
_WEEK_TITLE_RE = re.compile(r"^Week of\s+(\S+)$", re.IGNORECASE)
_OBJECTIVE_RE = re.compile(r"^\[([ xX])\]\s+([A-Za-z]{1,3}\d+)\s*[:–—-]?\s*(.*)$", re.DOTALL)
_LINK_RE = re.compile(r"https?://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9._-]+)/(pull|issues)/(\d+)")
_TAG_RE = re.compile(r"\[([A-Za-z]{1,3}\d+)\](?!\()")

_md = MarkdownIt("commonmark")


def _line(token: Token) -> int:
    return token.map[0] + 1 if token.map else 1


# --- profile ---------------------------------------------------------------


def _key_line(lines: list[str], key: str, default: int) -> int:
    pattern = re.compile(rf"^{re.escape(key)}\s*:")
    for i, line in enumerate(lines, start=1):
        if pattern.match(line):
            return i
    return default


def _str_list(value: Any) -> list[str] | None:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(v, str | int | float) for v in value):
        return [str(v) for v in value]
    return None


def parse_profile(path: Path) -> tuple[Profile | None, list[Issue]]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, [
            Issue(path, 1, "profile.md must start with YAML frontmatter between --- lines")
        ]
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return None, [Issue(path, 1, "frontmatter is not closed with a --- line")]
    try:
        data = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = mark.line + 2 if mark is not None else 1
        problem = getattr(exc, "problem", None) or "invalid YAML"
        return None, [Issue(path, line, f"frontmatter is not valid YAML: {problem}")]
    if not isinstance(data, dict):
        return None, [Issue(path, 2, "frontmatter must be key: value pairs")]

    issues: list[Issue] = []

    def at(key: str) -> int:
        return _key_line(lines, key, 1)

    def text_field(key: str, *, required: bool) -> str | None:
        value = data.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            if required:
                issues.append(Issue(path, 1, f"frontmatter is missing '{key}'"))
            return None
        if not isinstance(value, str | int | float) or isinstance(value, bool):
            issues.append(Issue(path, at(key), f"'{key}' must be text"))
            return None
        return str(value).strip()

    name = text_field("name", required=True)
    github = text_field("github", required=True)
    level = text_field("level", required=True)
    mentor = text_field("mentor", required=False)
    focus = text_field("focus", required=False) or ""

    if github:
        github = github.removeprefix("@")
    if mentor:
        mentor = mentor.removeprefix("@")
    if level:
        level = level.lower()
        if level not in LEVELS:
            issues.append(Issue(path, at("level"), f"level must be one of {', '.join(LEVELS)}"))

    lists: dict[str, list[str]] = {}
    for key in ("languages", "interests"):
        parsed = _str_list(data.get(key))
        if parsed is None:
            issues.append(Issue(path, at(key), f"'{key}' must be a list like [Rust, Python]"))
            parsed = []
        lists[key] = parsed

    active = data.get("active", True)
    if not isinstance(active, bool):
        issues.append(Issue(path, at("active"), "'active' must be true or false"))
        active = True

    known = {"name", "github", "level", "mentor", "languages", "interests", "focus", "active"}
    for key in data:
        if key not in known:
            issues.append(Issue(path, at(str(key)), f"unknown frontmatter key '{key}'", "warning"))

    if not (name and github and level):
        return None, issues
    profile = Profile(
        path=path,
        name=name,
        github=github,
        level=level,
        mentor=mentor,
        languages=lists["languages"],
        interests=lists["interests"],
        focus=focus,
        active=active,
    )
    return profile, issues


# --- month files -----------------------------------------------------------


def extract_evidence(text: str) -> list[Evidence]:
    tags = tuple(dict.fromkeys(t.upper() for t in _TAG_RE.findall(text)))
    return [
        Evidence(
            url=m[0],
            repo=f"{m[1]}/{m[2]}",
            kind="pull" if m[3] == "pull" else "issues",
            number=int(m[4]),
            objectives=tags,
        )
        for m in _LINK_RE.finditer(text)
    ]


def _merge_evidence(items: list[Evidence]) -> list[Evidence]:
    merged: dict[str, Evidence] = {}
    for ev in items:
        old = merged.get(ev.key)
        if old is None:
            merged[ev.key] = ev
        else:
            tags = tuple(dict.fromkeys((*old.objectives, *ev.objectives)))
            merged[ev.key] = Evidence(old.url, old.repo, old.kind, old.number, tags)
    return list(merged.values())


def parse_month(path: Path) -> tuple[MonthFile, list[Issue]]:
    month = path.stem
    result = MonthFile(path=path, month=month)
    issues: list[Issue] = []
    tokens = _md.parse(path.read_text(encoding="utf-8"))

    category: str | None = None  # inside a plan H2
    entry: WeekEntry | None = None  # inside a week H2
    section: str | None = None  # H3 inside a week
    depth = 0
    raw_evidence: list[Evidence] = []

    def close_week() -> None:
        nonlocal entry, raw_evidence
        if entry is not None:
            entry.evidence = _merge_evidence(raw_evidence)
        entry, raw_evidence = None, []

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open":
            title = tokens[i + 1].content.strip()
            line = _line(tok)
            if tok.tag == "h1":
                match = _PLAN_TITLE_RE.match(title)
                if match:
                    result.title_month = match[1]
                else:
                    issues.append(Issue(path, line, f"first heading should be '# Plan — {month}'"))
            elif tok.tag == "h2":
                close_week()
                category = section = None
                week_match = _WEEK_TITLE_RE.match(title)
                if title in CATEGORIES:
                    category = CATEGORIES[title]
                elif week_match:
                    try:
                        monday = date.fromisoformat(week_match[1])
                    except ValueError:
                        issues.append(Issue(path, line, f"'{title}': the date must be YYYY-MM-DD"))
                    else:
                        entry = WeekEntry(monday=monday, line=line)
                        result.weeks.append(entry)
                else:
                    issues.append(
                        Issue(path, line, f"unknown section '## {title}' is ignored", "warning")
                    )
            elif tok.tag == "h3":
                if entry is None:
                    issues.append(
                        Issue(
                            path, line, f"'### {title}' is outside a week and is ignored", "warning"
                        )
                    )
                    section = None
                else:
                    section = title
                    if title in entry.sections:
                        issues.append(
                            Issue(path, line, f"'### {title}' appears twice in this week")
                        )
                    entry.sections.setdefault(title, [])
                    entry.section_lines.setdefault(title, line)
            elif entry is not None and section is not None and title:
                entry.sections[section].append(title)  # h4+ inside a section is content
            i += 3  # heading_open, inline, heading_close
            continue

        if tok.type in ("bullet_list_open", "ordered_list_open"):
            depth += 1
        elif tok.type in ("bullet_list_close", "ordered_list_close"):
            depth -= 1
        elif tok.type == "inline":
            content = " ".join(tok.content.split())
            if content and category is not None and depth == 1:
                match = _OBJECTIVE_RE.match(content)
                if match:
                    result.objectives.append(
                        Objective(
                            id=match[2].upper(),
                            category=category,
                            text=match[3].strip(),
                            done=match[1] != " ",
                            line=_line(tok),
                        )
                    )
                else:
                    issues.append(
                        Issue(
                            path,
                            _line(tok),
                            "objectives look like '- [ ] C1: description' ('[x]' when done)",
                        )
                    )
            elif content and entry is not None and section is not None:
                entry.sections[section].append(content)
                raw_evidence.extend(extract_evidence(content))
        i += 1

    close_week()
    return result, issues


# --- folders ---------------------------------------------------------------


def load_contributor(folder: Path) -> tuple[Contributor | None, list[Issue]]:
    profile_path = folder / PROFILE_FILE
    if not profile_path.is_file():
        return None, [Issue(folder, 1, "contributor folder has no profile.md")]
    profile, issues = parse_profile(profile_path)
    months: list[MonthFile] = []
    for path in sorted(folder.iterdir()):
        if path.name == PROFILE_FILE or path.name.startswith("."):
            continue
        if path.is_file() and MONTH_FILE_RE.match(path.name):
            month, month_issues = parse_month(path)
            months.append(month)
            issues.extend(month_issues)
        else:
            issues.append(Issue(path, 1, "ignored: month files are named YYYY-MM.md", "warning"))
    if profile is None:
        return None, issues
    return Contributor(folder=folder, profile=profile, months=months), issues


def load_roster(root: Path) -> tuple[list[Contributor], list[Issue]]:
    base = root / "contributors"
    if not base.is_dir():
        return [], [Issue(base, 1, "no contributors/ folder found (is --root the repo root?)")]
    roster: list[Contributor] = []
    issues: list[Issue] = []
    for path in sorted(base.iterdir(), key=lambda p: p.name.lower()):
        if path.name.startswith("."):
            continue
        if not path.is_dir():
            issues.append(Issue(path, 1, "ignored: each contributor needs a folder", "warning"))
            continue
        contributor, found = load_contributor(path)
        issues.extend(found)
        if contributor is not None:
            roster.append(contributor)
    return roster, issues
