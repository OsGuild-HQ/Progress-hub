from pathlib import Path

import pytest

from conftest import write
from progress_bot.cli import main
from progress_bot.parser import parse_month


def run(repo: Path, *args: str, today: str = "2026-11-30") -> int:
    return main(["--root", str(repo), "--today", today, *args])


def test_new_then_week(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(repo, "new", "dave", "--name", "Dave", "--mentor", "@sam-sentinel") == 0
    folder = repo / "contributors/dave"
    assert "mentor: sam-sentinel" in (folder / "profile.md").read_text()
    assert run(repo, "week", "--user", "dave") == 0
    month, _ = parse_month(folder / "2026-11.md")
    assert [w.monday.isoformat() for w in month.weeks] == ["2026-11-30"]
    # Running it again doesn't duplicate the week.
    assert run(repo, "week", "--user", "dave") == 0
    assert "already has" in capsys.readouterr().out
    # Unfilled templates don't pass validation.
    assert run(repo, "validate") == 1
    assert run(repo, "new", "dave") == 2


def test_week_starts_new_month_with_open_objectives(repo: Path) -> None:
    assert run(repo, "week", "--user", "alice", "--date", "2026-12-09") == 0
    month, _ = parse_month(repo / "contributors/alice/2026-12.md")
    assert [o.id for o in month.objectives] == ["T2", "C1", "P1"]
    assert [w.monday.isoformat() for w in month.weeks] == ["2026-12-07"]


def test_validate_exit_codes_and_annotations(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert run(repo, "validate") == 0
    write(repo / "contributors/bob/2026-11.md", "# Plan — 2026-11\n\n## Week of 2026-11-25\n")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert run(repo, "validate", str(repo / "contributors/bob")) == 1
    out = capsys.readouterr().out
    assert "::error file=contributors/bob/2026-11.md,line=3::2026-11-25 is a Wednesday" in out
    assert "alice" not in out


def test_summarize_writes_report(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(repo, "summarize", "--no-github") == 0
    assert capsys.readouterr().out.strip() == "reports/weekly/2026-W48.md"
    text = (repo / "reports/weekly/2026-W48.md").read_text()
    assert text.startswith("# Guild Weekly Summary — 2026-W48")


def test_summarize_with_unreachable_llm(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:9/v1")
    assert run(repo, "summarize", "--no-github", "--llm", "--week", "2026-W48") == 0
    assert "AI-generated" not in (repo / "reports/weekly/2026-W48.md").read_text()


def test_monthly_and_bad_input(repo: Path) -> None:
    assert run(repo, "monthly", "--no-github", today="2026-12-01") == 0
    assert (repo / "reports/monthly/2026-11.md").is_file()
    assert run(repo, "summarize", "--week", "nope", "--no-github") == 2


def test_codeowners_check(repo: Path) -> None:
    assert run(repo, "codeowners", "--check") == 1
    assert run(repo, "codeowners") == 0
    assert run(repo, "codeowners", "--check") == 0


def test_check_ownership(repo: Path, tmp_path: Path) -> None:
    changed = write(tmp_path / "changed.txt", "contributors/bob/2026-11.md\n")
    args = ["check-ownership", "--author", "alice", "--base-root", str(repo)]
    assert run(repo, *args, "--changed-from", str(changed)) == 1
    assert run(repo, *args, "contributors/alice/2026-11.md") == 0


def test_root_after_subcommand(repo: Path) -> None:
    assert main(["validate", "--root", str(repo), "--today", "2026-11-30"]) == 0
