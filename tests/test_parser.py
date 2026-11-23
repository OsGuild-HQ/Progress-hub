from datetime import date
from pathlib import Path

from conftest import write
from progress_bot.parser import extract_evidence, load_roster, parse_month, parse_profile


def test_roster_loads_fixture(repo: Path) -> None:
    roster, issues = load_roster(repo)
    assert [c.login for c in roster] == ["alice", "bob", "carol", "sam-sentinel"]
    assert issues == []


def test_month_file_objectives_weeks_and_evidence(repo: Path) -> None:
    month, issues = parse_month(repo / "contributors/alice/2026-11.md")
    assert issues == []
    assert month.title_month == "2026-11"
    assert [(o.id, o.category, o.done) for o in month.objectives] == [
        ("T1", "technical", True),
        ("T2", "technical", False),
        ("C1", "contributions", False),
        ("P1", "community", False),
    ]
    # The "## Week of" inside a code block is not a week.
    assert [w.monday for w in month.weeks] == [
        date(2026, 11, 9),
        date(2026, 11, 16),
        date(2026, 11, 23),
    ]
    last = month.weeks[-1]
    assert len(last.items("Accomplished")) == 4
    assert last.blockers == ["Waiting for CI to be fixed upstream"]
    assert {(e.key, e.objectives) for e in last.evidence} == {
        ("fedimint/fedimint#7010", ("C1",)),
        ("fedimint/fedimint#142", ()),
    }


def test_none_items_are_not_blockers(repo: Path) -> None:
    month, _ = parse_month(repo / "contributors/bob/2026-11.md")
    assert month.weeks[0].blockers == []
    assert month.weeks[0].sections["Blockers"] == ["None"]


def test_evidence_tags_ignore_markdown_links() -> None:
    found = extract_evidence(
        "[C1] [the PR](https://github.com/a/b/pull/3) and https://github.com/a/b/pull/3"
    )
    assert [(e.key, e.objectives) for e in found] == [("a/b#3", ("C1",)), ("a/b#3", ("C1",))]


def test_malformed_objective_is_reported(tmp_path: Path) -> None:
    path = write(
        tmp_path / "2026-11.md",
        "# Plan — 2026-11\n\n## Technical Development\n\n- learn Rust\n",
    )
    month, issues = parse_month(path)
    assert month.objectives == []
    assert [i.line for i in issues] == [5]
    assert "[ ] C1" in issues[0].message


def test_bad_week_date_and_unknown_sections(tmp_path: Path) -> None:
    path = write(
        tmp_path / "2026-11.md",
        "# Plan for November\n\n## Week of 23/11/2026\n\n## Random\n\n### Orphan\n",
    )
    _, issues = parse_month(path)
    messages = [(i.severity, i.message) for i in issues]
    assert ("error", "first heading should be '# Plan — 2026-11'") in messages
    assert ("error", "'Week of 23/11/2026': the date must be YYYY-MM-DD") in messages
    assert ("warning", "unknown section '## Random' is ignored") in messages
    assert ("warning", "'### Orphan' is outside a week and is ignored") in messages


def test_profile_errors(tmp_path: Path) -> None:
    profile, issues = parse_profile(write(tmp_path / "a.md", "# no frontmatter\n"))
    assert profile is None
    assert "frontmatter" in issues[0].message

    profile, issues = parse_profile(write(tmp_path / "b.md", "---\nname: [oops\n---\n"))
    assert profile is None
    assert "not valid YAML" in issues[0].message

    profile, issues = parse_profile(
        write(tmp_path / "c.md", "---\nname: X\ngithub: '@x'\nlevel: Wizard\nlanguages: 3\n---\n")
    )
    assert profile is not None
    assert profile.github == "x"
    assert {i.message for i in issues} == {
        "level must be one of sentinel, spartan, adventurer",
        "'languages' must be a list like [Rust, Python]",
    }
    assert {i.line for i in issues} == {4, 5}

    profile, issues = parse_profile(write(tmp_path / "d.md", "---\nname: X\n---\n"))
    assert profile is None
    assert {i.message for i in issues} == {
        "frontmatter is missing 'github'",
        "frontmatter is missing 'level'",
    }


def test_folder_without_profile_and_stray_files(repo: Path) -> None:
    (repo / "contributors/ghost").mkdir()
    write(repo / "contributors/alice/notes.md", "hi\n")
    roster, issues = load_roster(repo)
    assert "ghost" not in [c.login for c in roster]
    assert {(i.path.name, i.severity) for i in issues} == {
        ("ghost", "error"),
        ("notes.md", "warning"),
    }
