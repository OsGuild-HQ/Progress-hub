from datetime import date
from pathlib import Path

from conftest import PLAN, WEEK, write
from progress_bot.validate import validate

TODAY = date(2026, 11, 30)


def messages(repo: Path) -> set[tuple[str, str]]:
    return {(i.severity, i.message) for i in validate(repo, TODAY)}


def test_fixture_is_valid(repo: Path) -> None:
    assert validate(repo, TODAY) == []


def add_month(repo: Path, login: str, month: str, body: str) -> Path:
    return write(repo / f"contributors/{login}/{month}.md", PLAN.format(month=month) + body)


def test_week_rules(repo: Path) -> None:
    add_month(
        repo,
        "bob",
        "2026-12",
        "\n"
        + WEEK.format(monday="2026-11-30")  # Monday, but belongs to November
        + "\n"
        + WEEK.format(monday="2026-12-02")  # a Wednesday
        + "\n"
        + WEEK.format(monday="2026-12-07"),  # in the future
    )
    found = messages(repo)
    assert ("error", "week of 2026-11-30 belongs in 2026-11.md") in found
    assert ("error", "2026-12-02 is a Wednesday; use that week's Monday (2026-11-30)") in found
    assert ("error", "week of 2026-12-07 is in the future") in found


def test_sections_must_exist_and_be_filled(repo: Path) -> None:
    week = WEEK.format(monday="2026-11-30").replace("### Learned\n\n- None\n", "")
    week = week.replace("### Blockers\n\n- None\n", "### Blockers\n\n- \n")
    path = repo / "contributors/bob/2026-11.md"
    path.write_text(path.read_text() + "\n" + week)
    found = messages(repo)
    assert ("error", "week of 2026-11-30 is missing '### Learned'") in found
    assert ("error", "'### Blockers' is empty; write 'None' if there is nothing to report") in found


def test_duplicate_weeks_and_objectives(repo: Path) -> None:
    path = repo / "contributors/bob/2026-11.md"
    text = path.read_text().replace("- [ ] C1: First documentation PR", "- [ ] T1: Again")
    path.write_text(text + "\n" + WEEK.format(monday="2026-11-02"))
    found = messages(repo)
    assert ("error", "objective ID T1 is used more than once") in found
    assert ("error", "week of 2026-11-02 appears twice") in found


def test_profile_rules(repo: Path) -> None:
    profile = repo / "contributors/bob/profile.md"
    profile.write_text(profile.read_text().replace("github: bob", "github: robert"))
    alice = repo / "contributors/alice/profile.md"
    alice.write_text(alice.read_text().replace("mentor: sam-sentinel", "mentor: nobody"))
    found = messages(repo)
    assert ("error", "folder is 'bob' but github is 'robert'; they must match") in found
    assert ("warning", "mentor @nobody has no profile here") in found


def test_unknown_objective_tag_warns(repo: Path) -> None:
    path = repo / "contributors/alice/2026-11.md"
    path.write_text(path.read_text().replace("[C1] https", "[C9] https"))
    assert (
        "warning",
        "https://github.com/fedimint/fedimint/pull/7010 is tagged [C9] "
        "but there is no objective C9",
    ) in messages(repo)
