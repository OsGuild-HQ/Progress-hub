# Contributing your progress

Setup takes about 15 minutes once. After that, the weekly update takes about 10.

## 1. Create your folder (once)

```bash
git clone https://github.com/sadeeqrabiu/progress-hub && cd progress-hub
uv sync
uv run progress-bot new <your-github-username> --name "Your Name" --level spartan --mentor <mentor-username>
uv run progress-bot codeowners
```

Then:

- In `contributors/<you>/profile.md`, fill in your languages, interests, focus and goals.
- In `contributors/<you>/<this-month>.md`, write your objectives. You need at least one in each category:
  - **Technical Development:** what you'll learn (`T1`, `T2`, ...)
  - **Open-Source Contributions:** what you'll ship (`C1`, ...)
  - **Community Participation:** how you'll help the Guild (`P1`, ...)

  Make each one specific enough that you and your mentor can tell when it's done.

Run `uv run progress-bot validate`, then open a pull request. Your mentor reviews it.

Only a Sentinel can change your `level` or `mentor`. Ask yours.

## 2. Every week

```bash
uv run progress-bot week --user <you>
```

This adds a `## Week of <Monday>` section to your month file. Fill in every heading, and write `None` where there's nothing to say:

- **Accomplished:** what you got done
- **Repositories:** what you worked in
- **Issues & PRs:** links. Tag the ones that count toward an objective: `[C1] https://github.com/org/repo/pull/12`
- **Learned:** concepts, tools, parts of a codebase
- **Blockers:** anything that stopped you. Be honest: this is how you get help
- **Support Needed:** what would unblock you
- **Next Week:** your plan

When an objective is done, tick it: `- [x] C1: ...`.

Check your work and open a PR:

```bash
uv run progress-bot validate contributors/<you>
```

## 3. A new month

The first `week` command in a new month starts the new month file for you and carries over the objectives you haven't ticked. At your monthly review with your mentor, keep, change or drop them, and add new ones.

## Rules the checker enforces

- The folder name and `github:` in your profile must match.
- Each week heading is the **Monday** of that week, in the month file for that Monday's month.
- Every weekly heading is present and not empty.
- Objective IDs are unique within a month.
- You can only change your own folder (and your mentees', if you're a mentor).

## Changing the bot

Bot code lives in `src/progress_bot/`. Run `task check` (or the `uv run` commands in the README) before opening a PR, and add tests in `tests/`.
