import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lambda"))
sys.path.insert(0, str(ROOT / "scripts"))

# The real config.py (with the API key) lives only in the hosted repo. Inject a
# dummy so `import config` works in tests; the key is never used (client mocked).
_dummy = types.ModuleType("config")
_dummy.ANTHROPIC_API_KEY = "sk-ant-test-dummy"
sys.modules.setdefault("config", _dummy)


@pytest.fixture
def alexa_request():
    """Build an Alexa request envelope dict for lambda_handler(event, ctx)."""
    def _build(request, session_new=False, attributes=None):
        return {
            "version": "1.0",
            "session": {
                "new": session_new,
                "sessionId": "amzn1.echo-api.session.test",
                "application": {"applicationId": "amzn1.ask.skill.test"},
                "user": {"userId": "amzn1.ask.account.test"},
                "attributes": attributes or {},
            },
            "context": {"System": {
                "application": {"applicationId": "amzn1.ask.skill.test"},
                "user": {"userId": "amzn1.ask.account.test"},
                "device": {"deviceId": "test", "supportedInterfaces": {}},
            }},
            "request": request,
        }
    return _build


def launch_request(locale="de-DE"):
    return {"type": "LaunchRequest", "requestId": "r1",
            "timestamp": "2026-07-21T10:00:00Z", "locale": locale}


def intent_request(name, slots=None, locale="de-DE"):
    intent = {"name": name, "confirmationStatus": "NONE"}
    if slots is not None:
        intent["slots"] = slots
    return {"type": "IntentRequest", "requestId": "r1",
            "timestamp": "2026-07-21T10:00:00Z", "locale": locale, "intent": intent}


def ask_query(text, locale="de-DE"):
    return intent_request("AskClaudeIntent",
                          {"query": {"name": "query", "value": text,
                                     "confirmationStatus": "NONE"}}, locale)


def session_ended_request(reason, error=None, locale="de-DE"):
    request = {"type": "SessionEndedRequest", "requestId": "r1",
               "timestamp": "2026-07-21T10:00:00Z", "locale": locale,
               "reason": reason}
    if error is not None:
        request["error"] = error
    return request
