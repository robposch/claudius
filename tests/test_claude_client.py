import pytest
import claude_client as cc
import settings


class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Msg:
    def __init__(self, text, stop_reason="end_turn"):
        self.content = [_Block(text)]
        self.stop_reason = stop_reason


class _FakeMessages:
    def __init__(self):
        self.last_kwargs = None
        self.reply = _Msg("hello")

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return self.reply


class _FakeClient:
    def __init__(self):
        self.messages = _FakeMessages()


@pytest.fixture
def fake(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(cc, "_get_client", lambda: client)
    return client


def test_haiku_request_shape(fake):
    out = cc.ask("hi", [], "haiku")
    assert out == "hello"
    kw = fake.messages.last_kwargs
    assert kw["model"] == "claude-haiku-4-5"
    assert kw["max_tokens"] == settings.MAX_TOKENS
    assert kw["system"] == settings.SYSTEM_PROMPT
    assert "extra_body" not in kw  # haiku: no effort/thinking
    assert "thinking" not in kw


def test_opus_uses_effort_via_extra_body(fake):
    cc.ask("hi", [], "opus")
    kw = fake.messages.last_kwargs
    assert kw["extra_body"] == {"output_config": {"effort": "low"}}


def test_sonnet_disables_thinking(fake):
    cc.ask("hi", [], "sonnet")
    kw = fake.messages.last_kwargs
    assert kw["thinking"] == {"type": "disabled"}
    assert kw["extra_body"] == {"output_config": {"effort": "low"}}


def test_request_extras_are_taken_from_settings(fake, monkeypatch):
    monkeypatch.setattr(settings, "MODEL_REQUEST_EXTRAS",
                        {"haiku": {"temperature": 0.2}}, raising=False)
    cc.ask("hi", [], "haiku")
    assert fake.messages.last_kwargs["temperature"] == 0.2
    cc.ask("hi", [], "sonnet")
    assert "thinking" not in fake.messages.last_kwargs


def test_unknown_model_key_falls_back_to_default_model(fake):
    cc.ask("hi", [], "turbo")
    assert fake.messages.last_kwargs["model"] == "claude-haiku-4-5"


def test_history_is_prepended(fake):
    cc.ask("new", [{"role": "user", "content": "old"}], "haiku")
    msgs = fake.messages.last_kwargs["messages"]
    assert msgs[0]["content"] == "old"
    assert msgs[-1] == {"role": "user", "content": "new"}


def test_answer_cut_off_by_max_tokens_ends_at_last_full_sentence(fake):
    fake.messages.reply = _Msg("Comets are icy. They orbit the sun. Their tails po",
                               stop_reason="max_tokens")
    assert cc.ask("hi", [], "haiku") == "Comets are icy. They orbit the sun."


def test_cut_off_answer_without_a_full_sentence_is_kept(fake):
    fake.messages.reply = _Msg("Pi is roughly 3.14 and goes on", stop_reason="max_tokens")
    assert cc.ask("hi", [], "haiku") == "Pi is roughly 3.14 and goes on"


def test_complete_answer_is_not_trimmed(fake):
    fake.messages.reply = _Msg("First. Second without a period")
    assert cc.ask("hi", [], "haiku") == "First. Second without a period"


def test_answer_without_text_is_empty(fake):
    fake.messages.reply = _Msg("   ")
    assert cc.ask("hi", [], "haiku") == ""
