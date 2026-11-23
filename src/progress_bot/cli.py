"""`progress-bot` command line."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path
from string import Template

from progress_bot import __version__
from progress_bot.analysis import analyse
from progress_bot.github import GitHubClient
from progress_bot.llm import LLMSettings, Narrator
from progress_bot.models import CATEGORIES, LEVELS, Activity, Contributor, Issue
from progress_bot.ownership import check_ownership, codeowners
from progress_bot.parser import load_roster, parse_month
from progress_bot.summarize import ContributorMonth, ReportContext, monthly_report, weekly_report
from progress_bot.validate import LOGIN_RE, validate
from progress_bot.weeks import Week, month_label, previous_month
from progress_bot.weeks import parse_month as month_range

CATEGORY_PREFIX = {"technical": "T", "contributions": "C", "community": "P"}


def _err(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 2


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _today(args: argparse.Namespace) -> date:
    return date.fromisoformat(args.today) if args.today else date.today()


def _template(root: Path, name: str) -> Template:
    path = root / "templates" / name
    if not path.is_file():
        raise FileNotFoundError(f"template {path} not found (is --root the repo root?)")
    return Template(path.read_text(encoding="utf-8"))


# --- new / week ------------------------------------------------------------


def _month_text(root: Path, month: str, carried: dict[str, list[str]]) -> str:
    values: dict[str, str] = {"month": month}
    for category in CATEGORIES.values():
        lines = carried.get(category) or [f"- [ ] {CATEGORY_PREFIX[category]}1: "]
        values[category] = "\n".join(lines)
    return _template(root, "month.md").substitute(values)


def _carry_over(folder: Path, month: str) -> dict[str, list[str]]:
    """Unfinished objectives from the latest earlier month, to start the new plan."""
    earlier = sorted(p for p in folder.glob("*.md") if p.stem < month and p.stem[:1].isdigit())
    if not earlier:
        return {}
    mf, _ = parse_month(earlier[-1])
    carried: dict[str, list[str]] = {}
    for o in mf.objectives:
        if not o.done:
            carried.setdefault(o.category, []).append(f"- [ ] {o.id}: {o.text}")
    return carried


def cmd_new(args: argparse.Namespace) -> int:
    root: Path = args.root
    login = args.login.removeprefix("@")
    if not LOGIN_RE.match(login):
        return _err(f"'{login}' is not a valid GitHub username")
    folder = root / "contributors" / login
    if folder.exists():
        return _err(f"{_rel(folder, root)} already exists")
    month = month_label(_today(args))
    try:
        profile = _template(root, "profile.md").substitute(
            name=args.name or login,
            github=login,
            level=args.level,
            mentor=(args.mentor or "").removeprefix("@"),
        )
        month_text = _month_text(root, month, {})
    except FileNotFoundError as exc:
        return _err(str(exc))
    folder.mkdir(parents=True)
    (folder / "profile.md").write_text(profile, encoding="utf-8")
    (folder / f"{month}.md").write_text(month_text, encoding="utf-8")
    print(f"Created {_rel(folder, root)}/: fill in profile.md and your objectives in {month}.md.")
    print("Then run `progress-bot codeowners` and open a pull request.")
    return 0


def cmd_week(args: argparse.Namespace) -> int:
    root: Path = args.root
    login = args.user.removeprefix("@")
    folder = root / "contributors" / login
    if not (folder / "profile.md").is_file():
        return _err(f"no profile at {_rel(folder, root)}/profile.md; run `progress-bot new` first")
    day = date.fromisoformat(args.date) if args.date else _today(args)
    week = Week.containing(day)
    path = folder / f"{week.month}.md"
    try:
        if not path.exists():
            path.write_text(
                _month_text(root, week.month, _carry_over(folder, week.month)), encoding="utf-8"
            )
            print(f"Started {_rel(path, root)}; review this month's objectives at the top.")
        mf, _ = parse_month(path)
        if any(w.monday == week.monday for w in mf.weeks):
            print(f"{_rel(path, root)} already has the week of {week.monday}.")
            return 0
        block = _template(root, "week.md").substitute(monday=week.monday.isoformat())
    except FileNotFoundError as exc:
        return _err(str(exc))
    text = path.read_text(encoding="utf-8").rstrip("\n")
    path.write_text(f"{text}\n\n{block}", encoding="utf-8")
    print(f"Added the week of {week.monday} to {_rel(path, root)}.")
    return 0


# --- validate --------------------------------------------------------------


def _print_issues(issues: list[Issue], root: Path) -> None:
    in_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    for i in issues:
        rel = _rel(i.path, root)
        if in_actions:
            message = i.message.replace("%", "%25").replace("\n", "%0A")
            print(f"::{i.severity} file={rel},line={i.line}::{message}")
        else:
            print(f"{rel}:{i.line}: {i.severity}: {i.message}")


def cmd_validate(args: argparse.Namespace) -> int:
    root: Path = args.root
    issues = validate(root, _today(args))
    if args.paths:
        wanted = [Path(p).resolve() for p in args.paths]
        issues = [
            i
            for i in issues
            if any(i.path.resolve() == w or w in i.path.resolve().parents for w in wanted)
        ]
    _print_issues(issues, root)
    errors = sum(i.severity == "error" for i in issues)
    warnings = len(issues) - errors
    roster, _ = load_roster(root)
    print(
        f"{len(roster)} contributors checked: {errors} errors, {warnings} warnings.",
        file=sys.stderr,
    )
    return 1 if errors else 0


# --- reports ---------------------------------------------------------------


def _github_client(args: argparse.Namespace) -> GitHubClient | None:
    if args.no_github:
        return None
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print(
            "warning: no GITHUB_TOKEN set; GitHub allows only 10 searches a minute without one",
            file=sys.stderr,
        )
    return GitHubClient(token, cache_dir=args.root / ".cache" / "github", today=_today(args))


def _write(text: str, out_dir: Path, name: str, args: argparse.Namespace) -> int:
    if args.stdout:
        sys.stdout.write(text)
        return 0
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    path.write_text(text, encoding="utf-8")
    print(f"Wrote {_rel(path, args.root)}", file=sys.stderr)
    print(_rel(path, args.root))  # stdout: the path, for scripts
    return 0


def _load_or_fail(root: Path) -> list[Contributor] | None:
    roster, issues = load_roster(root)
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        print(
            f"warning: {len(errors)} file problems; run `progress-bot validate`. "
            "Broken files are skipped.",
            file=sys.stderr,
        )
    if not roster:
        _err("no contributors found")
        return None
    return roster


def cmd_summarize(args: argparse.Namespace) -> int:
    root: Path = args.root
    week = Week.parse(args.week) if args.week else Week.containing(_today(args)).previous()
    roster = _load_or_fail(root)
    if roster is None:
        return 2
    gh = _github_client(args)

    def fetch(c: Contributor, w: Week) -> Activity:
        assert gh is not None
        return gh.activity(c.login, w.monday, w.sunday)

    results = [analyse(c, week, fetch if gh else None) for c in roster]
    narrator = Narrator(LLMSettings.from_env(os.environ)) if args.llm else None
    if narrator:
        for r in results:
            if r.expected and (r.entry is not None or (r.activity and not r.activity.empty)):
                r.narrative = narrator.narrate(r)
    ctx = ReportContext(
        generated=_today(args),
        github=gh is not None,
        llm=any(r.narrative for r in results),
    )
    out = args.out or root / "reports" / "weekly"
    return _write(weekly_report(results, week, ctx), out, f"{week.label}.md", args)


def cmd_monthly(args: argparse.Namespace) -> int:
    root: Path = args.root
    month = args.month or previous_month(_today(args))
    try:
        start, end = month_range(month)
    except ValueError as exc:
        return _err(str(exc))
    roster = _load_or_fail(root)
    if roster is None:
        return 2
    gh = _github_client(args)
    results: list[ContributorMonth] = []
    for c in roster:
        r = ContributorMonth(contributor=c, month=month)
        if gh is not None and c.profile.active:
            try:
                r.activity = gh.activity(c.login, start, end)
            except Exception as exc:
                r.github_error = str(exc)
        results.append(r)
    ctx = ReportContext(generated=_today(args), github=gh is not None, llm=False)
    out = args.out or root / "reports" / "monthly"
    return _write(monthly_report(results, month, ctx), out, f"{month}.md", args)


# --- codeowners / ownership ------------------------------------------------


def cmd_codeowners(args: argparse.Namespace) -> int:
    root: Path = args.root
    roster, _ = load_roster(root)
    text = codeowners(roster)
    path = root / ".github" / "CODEOWNERS"
    current = path.read_text(encoding="utf-8") if path.is_file() else ""
    if args.check:
        if current != text:
            print(
                "::error file=.github/CODEOWNERS::CODEOWNERS is out of date; run "
                "`progress-bot codeowners` and commit the result"
                if os.environ.get("GITHUB_ACTIONS") == "true"
                else "CODEOWNERS is out of date; run `progress-bot codeowners`."
            )
            return 1
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"Wrote {_rel(path, root)}", file=sys.stderr)
    return 0


def cmd_check_ownership(args: argparse.Namespace) -> int:
    changed = list(args.files)
    if args.changed_from:
        changed += [
            line.strip()
            for line in Path(args.changed_from).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    base, _ = load_roster(args.base_root)
    head, _ = load_roster(args.root)
    problems = check_ownership(args.author.removeprefix("@"), changed, base, head)
    for p in problems:
        print(f"::error::{p}" if os.environ.get("GITHUB_ACTIONS") == "true" else p)
    return 1 if problems else 0


# --- parser ----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="progress-bot",
        description="Validate OSGuild contributor reports and write Guild summaries.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--root", type=Path, default=Path(), help="repo root (default: .)")
    parser.add_argument("--today", help=argparse.SUPPRESS)  # fixed date for tests
    # The same options after the subcommand, e.g. `progress-bot validate --root x`.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", type=Path, default=argparse.SUPPRESS, help="repo root")
    common.add_argument("--today", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "new", help="create a contributor folder from the templates", parents=[common]
    )
    p.add_argument("login", help="GitHub username")
    p.add_argument("--name", help="display name (default: the username)")
    p.add_argument("--level", choices=LEVELS, default="spartan")
    p.add_argument("--mentor", help="mentor's GitHub username")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser(
        "week", help="add this week's report section to your month file", parents=[common]
    )
    p.add_argument("--user", required=True, help="your GitHub username")
    p.add_argument("--date", help="any day in the week (YYYY-MM-DD, default: today)")
    p.set_defaults(func=cmd_week)

    p = sub.add_parser(
        "validate", help="check contributor files; exits 1 on errors", parents=[common]
    )
    p.add_argument("paths", nargs="*", help="only report problems in these files or folders")
    p.set_defaults(func=cmd_validate)

    for name, help_text, period_flag, period_help in (
        (
            "summarize",
            "write the weekly Guild summary",
            "--week",
            "ISO week, e.g. 2026-W48 (default: last week)",
        ),
        ("monthly", "write the monthly review", "--month", "e.g. 2026-11 (default: last month)"),
    ):
        p = sub.add_parser(name, help=help_text, parents=[common])
        p.add_argument(period_flag, help=period_help)
        p.add_argument("--out", type=Path, help="output folder (default: reports/weekly|monthly)")
        p.add_argument("--stdout", action="store_true", help="print instead of writing a file")
        p.add_argument("--no-github", action="store_true", help="skip GitHub lookups")
        if name == "summarize":
            p.add_argument(
                "--llm",
                action="store_true",
                help="add AI narratives via OPENAI_BASE_URL / OPENAI_API_KEY / OPENAI_MODEL",
            )
        p.set_defaults(func=cmd_summarize if name == "summarize" else cmd_monthly)

    p = sub.add_parser(
        "codeowners", help="write .github/CODEOWNERS from the profiles", parents=[common]
    )
    p.add_argument("--check", action="store_true", help="exit 1 if CODEOWNERS is out of date")
    p.set_defaults(func=cmd_codeowners)

    p = sub.add_parser(
        "check-ownership", help="CI: check a PR only touches allowed folders", parents=[common]
    )
    p.add_argument("--author", required=True, help="PR author's GitHub username")
    p.add_argument("--base-root", type=Path, required=True, help="checkout of the target branch")
    p.add_argument("--changed-from", help="file listing changed paths, one per line")
    p.add_argument("files", nargs="*", help="changed paths")
    p.set_defaults(func=cmd_check_ownership)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        return _err(str(exc))
