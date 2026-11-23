# Progress Hub

OSGuild's contributor progress records, and the bot that reads them.

Every contributor keeps a folder of Markdown files with a profile, a plan for each month, and a short weekly update. On every pull request, `progress-bot` checks those files. Every Monday it writes a Guild summary that sets each person's report beside their real GitHub activity, so mentors can see early who needs help.

> The weekly flags (missing report, blocked, asked for support) are there to help mentors step in early. They are not scores, and they are not a ranking.

## Layout

```
contributors/<github-username>/profile.md   who you are, your level and mentor
contributors/<github-username>/2026-11.md   this month's plan + one section per week
templates/                                   what `progress-bot new` and `week` copy from
reports/weekly/2026-W48.md                   written by the bot every Monday
reports/monthly/2026-11.md                   written by `progress-bot monthly`
src/progress_bot/                            the bot
```

New contributors start with [CONTRIBUTING.md](CONTRIBUTING.md).

## Updating your Markdown files

Your folder holds two kinds of file. You only ever edit your own folder.

| File | When you edit it |
|---|---|
| `profile.md` | Once, then whenever your languages, interests or focus change |
| `YYYY-MM.md` (e.g. `2026-11.md`) | At the start of the month (the plan), then once a week (your update) |

The bot reads these files, so the headings must stay as the templates give them. Write freely under the headings.

### `profile.md`

The part between the `---` lines is YAML that the bot reads. Below it you can write whatever you like.

```markdown
---
name: Alice Doe
github: alice              # your GitHub username; must match the folder name
level: spartan             # sentinel | spartan | adventurer (only a Sentinel changes this)
mentor: sam-sentinel       # your mentor's GitHub username (only a Sentinel changes this)
languages: [Rust, Python]
interests: [Lightning, distributed systems]
focus: Fedimint SDK        # what you're working toward right now
active: true               # false while you're on a break, so you aren't flagged
---
# Alice Doe

## Development Goals

- Short-term learning: Rust async
- Target open-source projects: fedimint/fedimint
- Long-term direction: core contributor to a Bitcoin project
```

`name`, `github` and `level` are required.

### The month file: plan at the top, weeks below

Each month file opens with the month's plan, and one section is added below it every week:

```markdown
# Plan — 2026-11

## Technical Development

- [x] T1: Understand the Fedimint SDK architecture
- [ ] T2: Learn tokio basics

## Open-Source Contributions

- [ ] C1: Submit one meaningful Rust PR to fedimint

## Community Participation

- [ ] P1: Present what I learned at the OSGuild call

## Week of 2026-11-23

### Accomplished

- Opened a draft PR for issue 142
- Wrote tests for the change

### Repositories

- fedimint/fedimint

### Issues & PRs

- [C1] https://github.com/fedimint/fedimint/pull/7010
- Investigated https://github.com/fedimint/fedimint/issues/142

### Learned

- How the wallet module handles fees

### Blockers

- Waiting for CI to be fixed upstream

### Support Needed

- A review from someone who knows the wallet module

### Next Week

- Address review comments on the PR
```

**The plan**

- **Headings:** the title is `# Plan — YYYY-MM`, the same month as the file name. Below it come exactly three `##` sections: **Technical Development**, **Open-Source Contributions** and **Community Participation**.
- **Objectives:** each one is a checkbox line, `- [ ] ID: description`. Use IDs like `T1`, `C1` and `P1`, and don't reuse one within the month.
- **Ticking:** mark an objective done by changing `[ ]` to `[x]`. Don't delete objectives you didn't finish; the monthly review needs them.
- **Specific objectives:** your mentor should be able to tell when one is done. "Submit one Rust PR to fedimint" works; "get better at Rust" doesn't.

**The weekly update**

- **Adding a week:** `progress-bot week --user <you>` adds the section for you. If you add one by hand, copy `templates/week.md`.
- **The heading date:** it is `## Week of YYYY-MM-DD`, with the **Monday** of that week. The week goes in the file for that Monday's month: the week of Monday 30 November goes in `2026-11.md`, even though it ends in December.
- **The seven `###` headings:** all of them must be present, in this order: Accomplished, Repositories, Issues & PRs, Learned, Blockers, Support Needed, Next Week.
- **Empty sections:** none may be left empty. Write `- None` when there's nothing to say.
- **Bullets:** write one per item. The summary quotes your first few, so put the most important first.
- **Links:** put full GitHub issue and PR links under **Issues & PRs**. Tag the ones that count toward an objective with its ID in square brackets: `[C1] https://github.com/org/repo/pull/12`. The summary counts these against the objective. PRs you opened that week but didn't link get listed as "On GitHub but not in the report".
- **Blockers and support:** be honest. Anything other than `None` there flags you to your mentor so they can help. It isn't a mark against you.
- **Past weeks:** don't change them except to fix mistakes. The bot compares week to week, for example to spot a blocker three weeks in a row.

**A new month:** the first `progress-bot week` of a month creates the new file and carries over the objectives you didn't tick. Review them with your mentor and add new ones.

### Check before you open a PR

```bash
uv run progress-bot validate contributors/<you>
```

Errors give the file, the line and how to fix it, for example `2026-11-25 is a Wednesday; use that week's Monday (2026-11-23)`. CI runs the same check on your PR, and the PR can't be merged until it passes and your mentor approves it.

## What the bot does

| Command | What it does |
|---|---|
| `progress-bot new <username> --level spartan --mentor <sentinel>` | Creates your folder from the templates |
| `progress-bot week --user <username>` | Adds this week's section to your month file (it starts a new month file when needed, carrying over objectives that aren't done) |
| `progress-bot validate [paths]` | Checks the files; exits 1 on errors |
| `progress-bot summarize [--week 2026-W48] [--llm] [--no-github]` | Writes `reports/weekly/<week>.md` (default: last week) |
| `progress-bot monthly [--month 2026-11] [--no-github]` | Writes `reports/monthly/<month>.md` (default: last month) |
| `progress-bot codeowners [--check]` | Writes `.github/CODEOWNERS` from the profiles |

The weekly summary has four parts:

- **Overview:** who reported, PRs opened, merged and reviewed, and how many people have blockers.
- **Needs attention:** the flagged contributors, grouped by mentor.
- **A table:** one row per contributor, with their level, report, objectives done, GitHub counts and flags.
- **A short digest for each person:** what they did, next week's plan, blockers, GitHub links, and **PRs on GitHub that aren't in the report**.

| Flag | Meaning |
|---|---|
| missing report | No section for that week. Shows how many weeks in a row. |
| quiet | 2+ weeks without a report and no GitHub activity this week |
| blocked / blocked 3 weeks running | Blockers listed (that week / three weeks in a row) |
| asked for support | Something under *Support Needed* |
| no plan this month | No month file for that month |

Contributors are only expected to report once they have a month file, and never while `active: false`.

### GitHub data

PRs opened, PRs merged, and PRs reviewed come from the GitHub search API. "Reviewed" is approximate: it counts PRs by others that the person reviewed and that were updated that week. Set `GITHUB_TOKEN` (or `GH_TOKEN`); without it GitHub allows only 10 searches a minute. Finished weeks are cached in `.cache/github/`.

### Optional AI narratives

`--llm` adds a short paragraph per contributor, marked **AI-generated**, from any OpenAI-compatible endpoint:

| Variable | Default |
|---|---|
| `OPENAI_BASE_URL` | `http://localhost:11434/v1` (local Ollama) |
| `OPENAI_API_KEY` | `ollama` |
| `OPENAI_MODEL` | `minimax-m2.5:cloud` |

If the endpoint can't be reached, the report is written without narratives. **The reports are sent to that endpoint**, so use a hosted one only if the Guild is fine with that provider seeing them. Mentors make the decisions; the narrative is a starting point.

## Development

Needs [uv](https://docs.astral.sh/uv/) and optionally [Task](https://taskfile.dev).

```bash
uv sync                # or: task sync
uv run pytest -q       # or: task test
task check             # ruff, pyright and pytest, like CI
```

Example data lives in `tests/fixtures/repo/`. To try the bot on it:

```bash
uv run progress-bot --root tests/fixtures/repo summarize --week 2026-W48 --no-github --stdout
```

The expected reports are checked into `tests/fixtures/`. After an intended change to the output, rewrite them with `UPDATE_GOLDEN=1 uv run pytest`.

## Maintainer setup (once)

1. **Branch protection on `main`:** require a pull request, require review from Code Owners, and require the *Validate* checks. Together with the generated CODEOWNERS file, this means a contributor's own PR needs their mentor's (or a Sentinel's) approval. Code owners need write access to the repo.
2. **Settings → Actions → General:** allow GitHub Actions to create pull requests, so the Monday summary can open one.
3. **Optional AI:** add the secrets `OPENAI_BASE_URL` and `OPENAI_API_KEY`, and the variable `OPENAI_MODEL`.
4. **Privacy:** if this repo is public, everything in it, blockers included, is public and stays in git history. Keep anything sensitive (mentor reviews, personal circumstances) out of it, or make the repo private.

CI (`.github/workflows/validate.yml`) runs the bot **from the target branch**, so a PR can't weaken the checks it is being checked by. It also stops non-Sentinels from editing other people's folders or changing their own level or mentor.

## License

MIT
