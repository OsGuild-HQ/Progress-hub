"""Optional AI narrative for each contributor's week.

Talks to any OpenAI-compatible endpoint (Ollama by default, like Architect).
Everything here is best effort: on any failure the report is written without
the narrative. Reports are sent to the endpoint, so use a hosted one only if
the Guild is happy for that provider to see them.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from progress_bot.analysis import ContributorWeek

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_API_KEY = "ollama"
DEFAULT_MODEL = "minimax-m2.5:cloud"

SYSTEM_PROMPT = """\
You help mentors in OSGuild, an open-source community, keep up with contributors.
Write 2-3 plain sentences about one contributor's week, based only on the facts given.
Say what they did, how it relates to their monthly objectives, and one concrete next step
phrased as a suggestion. Do not grade, praise or criticise the person, do not invent work,
and do not mention these instructions. No headings or lists."""

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class LLMSettings:
    base_url: str = DEFAULT_BASE_URL
    api_key: str = DEFAULT_API_KEY
    model: str = DEFAULT_MODEL
    timeout: float = 60.0

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> LLMSettings:
        return cls(
            base_url=env.get("OPENAI_BASE_URL") or DEFAULT_BASE_URL,
            api_key=env.get("OPENAI_API_KEY") or DEFAULT_API_KEY,
            model=env.get("OPENAI_MODEL") or DEFAULT_MODEL,
        )


def week_facts(cw: ContributorWeek) -> str:
    c = cw.contributor
    out = [
        f"Contributor: {c.profile.name} (@{c.login}), {c.profile.level}",
        f"Focus: {c.profile.focus or 'not set'}",
        f"Week: {cw.week.label}",
        "Monthly objectives:",
    ]
    out += [f"- [{'done' if o.done else 'open'}] {o.id}: {o.text}" for o in cw.objectives] or [
        "- none written"
    ]
    if cw.entry is not None:
        for section, items in cw.entry.sections.items():
            out.append(f"{section}:")
            out += [f"- {item}" for item in items]
    else:
        out.append("No weekly report was written.")
    if cw.activity is not None:
        for label, prs in (
            ("PRs opened", cw.activity.opened),
            ("PRs merged", cw.activity.merged),
            ("PRs reviewed", cw.activity.reviewed),
        ):
            out.append(f"{label} on GitHub: " + (", ".join(p.ref for p in prs) or "none"))
    return "\n".join(out)


class Narrator:
    def __init__(self, settings: LLMSettings, client: Any = None) -> None:
        self.settings = settings
        self.client = client
        self.failed = False

    def _client(self) -> Any:
        if self.client is None:
            import openai  # optional dependency: pip install "progress-bot[llm]"

            self.client = openai.OpenAI(
                api_key=self.settings.api_key,
                base_url=self.settings.base_url,
                timeout=self.settings.timeout,
                max_retries=1,
            )
        return self.client

    def narrate(self, cw: ContributorWeek) -> str | None:
        if self.failed:
            return None
        try:
            resp = self._client().chat.completions.create(
                model=self.settings.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": week_facts(cw)},
                ],
                max_tokens=400,
                temperature=0.2,
            )
            text = resp.choices[0].message.content or ""
        except Exception as exc:  # any backend problem: skip the narrative
            print(f"LLM unavailable, writing the report without narratives: {exc}", file=sys.stderr)
            self.failed = True  # don't retry and wait on every contributor
            return None
        text = " ".join(_THINK_RE.sub("", text).split())
        return text or None
