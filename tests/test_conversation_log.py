import json
import urllib.request

import conversation_log as clog
import settings


def test_disabled_does_nothing(monkeypatch):
    monkeypatch.setattr(settings, "LOG_CONVERSATIONS", False)
    posted = []
    monkeypatch.setattr(clog, "_post", lambda url, payload: posted.append(payload))
    clog.record("q", "a", "haiku", "de-DE")
    assert posted == []


def test_enabled_posts_when_webhook_set(monkeypatch):
    monkeypatch.setattr(settings, "LOG_CONVERSATIONS", True)
    monkeypatch.setattr(settings, "LOG_WEBHOOK_URL", "https://example.com/hook")
    captured = {}
    monkeypatch.setattr(clog, "_post", lambda url, payload: captured.update(
        url=url, payload=payload))
    clog.record("q", "a", "haiku", "de-DE")
    assert captured["url"] == "https://example.com/hook"
    assert captured["payload"]["question"] == "q"
    assert captured["payload"]["answer"] == "a"
    assert captured["payload"]["model"] == "haiku"
    assert captured["payload"]["locale"] == "de-DE"


def test_never_raises_on_post_failure(monkeypatch):
    monkeypatch.setattr(settings, "LOG_CONVERSATIONS", True)
    monkeypatch.setattr(settings, "LOG_WEBHOOK_URL", "https://example.com/hook")

    def boom(url, payload):
        raise RuntimeError("down")
    monkeypatch.setattr(clog, "_post", boom)
    clog.record("q", "a", "haiku", "de-DE")  # must not raise


def test_post_sends_json_with_a_short_timeout(monkeypatch):
    sent = {}

    class _Response:
        def close(self):
            sent["closed"] = True

    def fake_urlopen(req, timeout):
        sent.update(url=req.full_url, body=req.data, timeout=timeout,
                    content_type=req.get_header("Content-type"))
        return _Response()
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    clog._post("https://example.com/hook", {"question": "wie spät", "answer": "früh"})

    assert sent["url"] == "https://example.com/hook"
    assert json.loads(sent["body"].decode("utf-8")) == {
        "question": "wie spät", "answer": "früh"}
    assert sent["content_type"] == "application/json"
    # Worst case is added to the Claude timeout inside Alexa's ~8 s window.
    assert settings.TIMEOUT_SECONDS + sent["timeout"] <= 7.0
    assert sent["closed"] is True
