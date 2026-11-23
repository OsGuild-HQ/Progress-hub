from pathlib import Path
from types import SimpleNamespace
from typing import Any

from progress_bot.analysis import analyse
from progress_bot.llm import DEFAULT_BASE_URL, LLMSettings, Narrator, week_facts
from progress_bot.parser import load_roster
from progress_bot.weeks import Week


class FakeClient:
    def __init__(self, reply: str | Exception) -> None:
        self.reply = reply
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.reply, Exception):
            raise self.reply
        message = SimpleNamespace(content=self.reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def alice_week(repo: Path):
    roster, _ = load_roster(repo)
    alice = next(c for c in roster if c.login == "alice")
    return analyse(alice, Week.parse("2026-W48"))


def test_narrate_strips_thinking(repo: Path) -> None:
    fake = FakeClient("<think>hmm</think>  Alice opened a draft PR.\n Next, address review. ")
    narrator = Narrator(LLMSettings(model="m"), client=fake)
    assert narrator.narrate(alice_week(repo)) == "Alice opened a draft PR. Next, address review."
    prompt = fake.calls[0]["messages"][1]["content"]
    assert "[done] T1: Understand the Fedimint SDK architecture" in prompt
    assert "Waiting for CI to be fixed upstream" in prompt
    assert fake.calls[0]["model"] == "m"


def test_failure_disables_narrator(repo: Path) -> None:
    fake = FakeClient(ConnectionError("refused"))
    narrator = Narrator(LLMSettings(), client=fake)
    cw = alice_week(repo)
    assert narrator.narrate(cw) is None
    assert narrator.narrate(cw) is None
    assert len(fake.calls) == 1


def test_settings_from_env_ignore_blanks() -> None:
    s = LLMSettings.from_env({"OPENAI_BASE_URL": "", "OPENAI_MODEL": "llama3"})
    assert s.base_url == DEFAULT_BASE_URL
    assert s.model == "llama3"


def test_facts_without_report(repo: Path) -> None:
    roster, _ = load_roster(repo)
    bob = next(c for c in roster if c.login == "bob")
    assert "No weekly report was written." in week_facts(analyse(bob, Week.parse("2026-W48")))
