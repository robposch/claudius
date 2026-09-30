"""Best-effort conversation history. Off by default; never raises. Enabled via
settings.LOG_CONVERSATIONS.

The webhook POST is synchronous: it runs before the answer is spoken and can
delay it by up to _POST_TIMEOUT seconds."""

import json
import logging
import urllib.request

import settings

logger = logging.getLogger(__name__)

# Seconds. Adds to settings.TIMEOUT_SECONDS in the worst case, and the two
# together must stay inside Alexa's ~8 s window.
_POST_TIMEOUT = 0.5


def _post(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=_POST_TIMEOUT).close()


def record(question, answer, model, locale):
    if not settings.LOG_CONVERSATIONS:
        return
    payload = {"locale": locale, "model": model,
               "question": question, "answer": answer}
    logger.info("conversation %s", json.dumps(payload, ensure_ascii=False))
    if settings.LOG_WEBHOOK_URL:
        try:
            _post(settings.LOG_WEBHOOK_URL, payload)
        except Exception:
            logger.warning("conversation webhook failed", exc_info=True)
