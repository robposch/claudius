import logging

import anthropic
import httpx
import pytest

import lambda_function as lf
import settings
from conftest import ask_query, intent_request, launch_request, session_ended_request


@pytest.fixture(autouse=True)
def no_real_claude(monkeypatch):
    monkeypatch.setattr(lf.claude_client, "ask", lambda q, h, m: f"ANSWER:{q}")


def _resp(event):
    return lf.lambda_handler(event, None)["response"]


def _ask_raises(monkeypatch, exc):
    def ask(question, history, model_key):
        raise exc
    monkeypatch.setattr(lf.claude_client, "ask", ask)


def _api_request():
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def test_launch_greets_and_keeps_open(alexa_request):
    r = _resp(alexa_request(launch_request(), session_new=True))
    assert "Claudius" in r["outputSpeech"]["ssml"]
    assert r["shouldEndSession"] is False
    assert any(d["type"] == "Dialog.ElicitSlot" for d in r.get("directives", []))


def test_launch_uses_locale_persona_and_language(alexa_request):
    r = _resp(alexa_request(launch_request("fr-FR"), session_new=True))
    assert "Ici Clauda" in r["outputSpeech"]["ssml"]


def test_launch_in_unlisted_locale_uses_default_persona(alexa_request, monkeypatch):
    monkeypatch.setattr(settings, "DEFAULT_PERSONA_NAME", "Testus", raising=False)
    r = _resp(alexa_request(launch_request("es-ES"), session_new=True))
    assert "This is Testus" in r["outputSpeech"]["ssml"]


def test_question_answers_and_keeps_open(alexa_request):
    r = _resp(alexa_request(ask_query("was ist ein komet")))
    assert "ANSWER:was ist ein komet" in r["outputSpeech"]["ssml"]
    assert r["shouldEndSession"] is False
    assert r["reprompt"]["outputSpeech"]["ssml"]  # a reprompt is set


def test_answer_is_appended_to_history(alexa_request):
    out = lf.lambda_handler(alexa_request(ask_query("was ist ein komet")), None)
    assert out["sessionAttributes"]["history"] == [
        {"role": "user", "content": "was ist ein komet"},
        {"role": "assistant", "content": "ANSWER:was ist ein komet"},
    ]


def test_history_keeps_only_the_newest_turns(alexa_request, monkeypatch):
    monkeypatch.setattr(lf, "HISTORY_MAX_ENTRIES", 4)
    old = [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"},
           {"role": "user", "content": "q2"}, {"role": "assistant", "content": "a2"}]
    out = lf.lambda_handler(
        alexa_request(ask_query("q3"), attributes={"history": old}), None)
    assert [m["content"] for m in out["sessionAttributes"]["history"]] == [
        "q2", "a2", "q3", "ANSWER:q3"]


def test_history_is_sent_to_claude(alexa_request, monkeypatch):
    seen = {}

    def ask(question, history, model_key):
        seen.update(question=question, history=history, model_key=model_key)
        return "ok"
    monkeypatch.setattr(lf.claude_client, "ask", ask)
    old = [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"}]
    _resp(alexa_request(ask_query("q2"), attributes={"history": old, "model": "opus"}))
    assert seen == {"question": "q2", "history": old, "model_key": "opus"}


def test_empty_query_reprompts_without_calling_claude(alexa_request, monkeypatch):
    _ask_raises(monkeypatch, AssertionError("Claude must not be called"))
    r = _resp(alexa_request(ask_query("   ")))
    assert settings.STRINGS["de"]["reprompt"] in r["outputSpeech"]["ssml"]
    assert r["shouldEndSession"] is False


def test_timeout_gives_retry_hint_and_keeps_open(alexa_request, monkeypatch):
    _ask_raises(monkeypatch, anthropic.APITimeoutError(request=_api_request()))
    out = lf.lambda_handler(alexa_request(ask_query("was ist ein komet")), None)
    assert settings.STRINGS["de"]["timeout"] in out["response"]["outputSpeech"]["ssml"]
    assert out["response"]["shouldEndSession"] is False
    assert "history" not in out["sessionAttributes"]


def test_api_error_gives_error_message_and_keeps_open(alexa_request, monkeypatch):
    _ask_raises(monkeypatch, anthropic.APIError("boom", _api_request(), body=None))
    out = lf.lambda_handler(alexa_request(ask_query("was ist ein komet")), None)
    assert settings.STRINGS["de"]["error"] in out["response"]["outputSpeech"]["ssml"]
    assert out["response"]["shouldEndSession"] is False
    assert "history" not in out["sessionAttributes"]


def test_empty_answer_is_spoken_as_error_and_not_remembered(alexa_request, monkeypatch):
    monkeypatch.setattr(lf.claude_client, "ask", lambda q, h, m: "")
    out = lf.lambda_handler(alexa_request(ask_query("was ist ein komet")), None)
    assert settings.STRINGS["de"]["error"] in out["response"]["outputSpeech"]["ssml"]
    assert "history" not in out["sessionAttributes"]


def test_unexpected_exception_is_spoken_as_error(alexa_request, monkeypatch):
    _ask_raises(monkeypatch, RuntimeError("bug"))
    r = _resp(alexa_request(ask_query("what is a comet", locale="en-US")))
    assert settings.STRINGS["en"]["error"] in r["outputSpeech"]["ssml"]
    assert r["shouldEndSession"] is False


def test_filler_is_skipped_on_fast_models(alexa_request, monkeypatch):
    spoken = []
    monkeypatch.setattr(lf, "send_progressive_response",
                        lambda handler_input, text: spoken.append(text))
    _resp(alexa_request(ask_query("frage"), attributes={"model": "haiku"}))
    assert spoken == []


def test_filler_is_spoken_on_slow_models(alexa_request, monkeypatch):
    spoken = []
    monkeypatch.setattr(lf, "send_progressive_response",
                        lambda handler_input, text: spoken.append(text))
    _resp(alexa_request(ask_query("frage"), attributes={"model": "opus"}))
    assert spoken == [settings.STRINGS["de"]["thinking"]]


def test_stop_phrase_ends_session(alexa_request):
    r = _resp(alexa_request(ask_query("stopp")))
    assert r["shouldEndSession"] is True


def test_dismissal_ends_session(alexa_request):
    r = _resp(alexa_request(ask_query("egal")))
    assert r["shouldEndSession"] is True


def test_model_switch_sets_model_stays_open(alexa_request):
    out = lf.lambda_handler(alexa_request(ask_query("benutze opus")), None)
    assert "Opus" in out["response"]["outputSpeech"]["ssml"]
    assert out["response"]["shouldEndSession"] is False
    assert out["sessionAttributes"]["model"] == "opus"


def test_stop_intent_ends_session(alexa_request):
    r = _resp(alexa_request(intent_request("AMAZON.StopIntent")))
    assert r["shouldEndSession"] is True


def test_help_explains_in_request_language(alexa_request):
    r = _resp(alexa_request(intent_request("AMAZON.HelpIntent", locale="en-US")))
    assert settings.STRINGS["en"]["help"] in r["outputSpeech"]["ssml"]
    assert r["shouldEndSession"] is False


def test_fallback_asks_again_and_keeps_open(alexa_request):
    r = _resp(alexa_request(intent_request("AMAZON.FallbackIntent", locale="fr-FR")))
    assert settings.STRINGS["fr"]["fallback"] in r["outputSpeech"]["ssml"]
    assert r["shouldEndSession"] is False


def test_session_end_error_is_logged(alexa_request, caplog):
    error = {"type": "INVALID_RESPONSE", "message": "Invalid Directive: Dialog.ElicitSlot"}
    with caplog.at_level(logging.WARNING, logger="lambda_function"):
        lf.lambda_handler(alexa_request(session_ended_request("ERROR", error)), None)
    assert "Invalid Directive: Dialog.ElicitSlot" in caplog.text


class _FakeAttributes:
    def __init__(self, persistent=None, broken=False):
        self.session_attributes = {}
        self._persistent = dict(persistent or {})
        self._broken = broken
        self.saved = None

    @property
    def persistent_attributes(self):
        if self._broken:
            raise RuntimeError("no persistence adapter")
        return self._persistent

    def save_persistent_attributes(self):
        self.saved = dict(self._persistent)


class _FakeInput:
    def __init__(self, attributes):
        self.attributes_manager = attributes


def test_model_choice_is_read_from_persistence_once_per_session():
    attrs = _FakeAttributes(persistent={"model": "sonnet"})
    assert lf.get_model_key(_FakeInput(attrs)) == "sonnet"
    assert attrs.session_attributes["model"] == "sonnet"


def test_model_falls_back_to_default_without_persistence(monkeypatch):
    monkeypatch.setattr(settings, "DEFAULT_MODEL", "sonnet")
    attrs = _FakeAttributes(broken=True)
    assert lf.get_model_key(_FakeInput(attrs)) == "sonnet"


def test_set_model_persists_the_choice():
    attrs = _FakeAttributes(persistent={"model": "haiku"})
    lf.set_model(_FakeInput(attrs), "opus")
    assert attrs.saved == {"model": "opus"}
    assert attrs.session_attributes["model"] == "opus"


def test_set_model_survives_broken_persistence():
    attrs = _FakeAttributes(broken=True)
    lf.set_model(_FakeInput(attrs), "opus")  # must not raise
    assert attrs.session_attributes["model"] == "opus"
