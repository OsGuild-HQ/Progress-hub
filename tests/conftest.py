from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A copy of the sample repo: Sam (Sentinel), Alice, Bob and inactive Carol."""
    dest = tmp_path / "repo"
    shutil.copytree(FIXTURES / "repo", dest)
    return dest


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


WEEK = """\
## Week of {monday}

### Accomplished

- Did a thing

### Repositories

- org/repo

### Issues & PRs

- None

### Learned

- None

### Blockers

- None

### Support Needed

- None

### Next Week

- More things
"""

PLAN = """\
# Plan — {month}

## Technical Development

- [ ] T1: Learn something

## Open-Source Contributions

- [ ] C1: Ship something

## Community Participation

- [ ] P1: Share something
"""
