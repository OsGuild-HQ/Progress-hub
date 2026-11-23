from pathlib import Path

from progress_bot.ownership import check_ownership, codeowners
from progress_bot.parser import load_roster


def rosters(repo: Path):
    base, _ = load_roster(repo)
    head, _ = load_roster(repo)
    return base, head


def test_codeowners(repo: Path) -> None:
    roster, _ = load_roster(repo)
    text = codeowners(roster)
    assert "* @sam-sentinel\n" in text
    assert "/contributors/alice/ @alice @sam-sentinel\n" in text
    assert "/contributors/sam-sentinel/ @sam-sentinel\n" in text


def test_contributor_may_edit_own_folder_only(repo: Path) -> None:
    base, head = rosters(repo)
    assert (
        check_ownership("alice", ["contributors/alice/2026-11.md", "README.md"], base, head) == []
    )
    assert check_ownership("alice", ["contributors/bob/2026-11.md"], base, head) == [
        "contributors/bob/2026-11.md: @alice can only change contributors/alice/"
    ]


def test_sentinels_and_mentors(repo: Path) -> None:
    base, head = rosters(repo)
    assert check_ownership("sam-sentinel", ["contributors/bob/profile.md"], base, head) == []


def test_no_self_promotion(repo: Path) -> None:
    base, _ = load_roster(repo)
    profile = repo / "contributors/alice/profile.md"
    profile.write_text(
        profile.read_text()
        .replace("level: spartan", "level: sentinel")
        .replace("mentor: sam-sentinel", "mentor: bob")
    )
    head, _ = load_roster(repo)
    problems = check_ownership("alice", ["contributors/alice/profile.md"], base, head)
    assert problems == [
        "contributors/alice/profile.md: level changes (spartan → sentinel) "
        "must be made by a Sentinel",
        "contributors/alice/profile.md: mentor changes must be made by a Sentinel",
    ]


def test_new_contributor(repo: Path) -> None:
    base, _ = load_roster(repo)
    folder = repo / "contributors/dave"
    folder.mkdir()
    (folder / "profile.md").write_text("---\nname: Dave\ngithub: dave\nlevel: sentinel\n---\n")
    head, _ = load_roster(repo)
    assert check_ownership("dave", ["contributors/dave/profile.md"], base, head) == [
        "contributors/dave/profile.md: only a Sentinel can add a new Sentinel"
    ]


def test_bootstrap_without_sentinels_allows_anything() -> None:
    assert check_ownership("founder", ["contributors/.gitkeep"], [], []) == []
