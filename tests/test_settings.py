import json
from pathlib import Path

import pytest
import settings

MODELS_DIR = (Path(__file__).resolve().parent.parent
              / "skill-package" / "interactionModels" / "custom")


def test_default_settings_validate():
    settings.validate()  # ships valid


def test_bad_default_model(monkeypatch):
    monkeypatch.setattr(settings, "DEFAULT_MODEL", "hiaku")
    with pytest.raises(ValueError, match="DEFAULT_MODEL"):
        settings.validate()


def test_fast_model_unknown(monkeypatch):
    monkeypatch.setattr(settings, "FAST_MODELS", frozenset({"turbo"}))
    with pytest.raises(ValueError, match="FAST_MODELS"):
        settings.validate()


def test_model_word_unknown(monkeypatch):
    monkeypatch.setattr(settings, "MODEL_WORDS", {"turbo": "turbo"})
    with pytest.raises(ValueError, match="MODEL_WORDS"):
        settings.validate()


def test_request_extras_for_unknown_model(monkeypatch):
    monkeypatch.setattr(settings, "MODEL_REQUEST_EXTRAS", {"turbo": {}}, raising=False)
    with pytest.raises(ValueError, match="MODEL_REQUEST_EXTRAS"):
        settings.validate()


def test_bad_max_tokens(monkeypatch):
    monkeypatch.setattr(settings, "MAX_TOKENS", 0)
    with pytest.raises(ValueError, match="MAX_TOKENS"):
        settings.validate()


@pytest.mark.parametrize("url", ["notaurl", "http://example.com/hook"])
def test_webhook_must_be_https(monkeypatch, url):
    monkeypatch.setattr(settings, "LOG_WEBHOOK_URL", url)
    with pytest.raises(ValueError, match="LOG_WEBHOOK_URL"):
        settings.validate()


def test_persona_names_match_the_invocation_names():
    """The Lambda greets with PERSONA_NAMES; Alexa only recognizes the
    invocationName. A mismatch introduces the skill by a name nobody can invoke."""
    invocation_names = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        ["interactionModel"]["languageModel"]["invocationName"]
        for path in MODELS_DIR.glob("*.json")
    }
    spoken = {locale: name.lower() for locale, name in settings.PERSONA_NAMES.items()}
    assert spoken == invocation_names
