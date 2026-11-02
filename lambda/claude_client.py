"""Thin wrapper around the Anthropic Messages API for voice-length answers."""

import logging
import re
import time

import anthropic

import config
import settings

_client = None
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# The end of a sentence: closing punctuation followed by whitespace.
_SENTENCE_END_RE = re.compile(r"[.!?](?=\s)")


def _get_client():
    """Create the Anthropic client on first use (keeps import cheap and
    key-free, which also lets the module import under test)."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic(
            api_key=config.ANTHROPIC_API_KEY,
            timeout=settings.TIMEOUT_SECONDS,
            max_retries=0,  # no time to retry inside Alexa's response window
        )
    return _client


def _drop_unfinished_sentence(text):
    """Cut an answer that ran into max_tokens back to its last full sentence,
    so Alexa does not stop mid-word. Kept as is when no sentence is complete."""
    ends = [match.end() for match in _SENTENCE_END_RE.finditer(text)]
    return text[:ends[-1]] if ends else text


def _answer_blocks(content):
    """The blocks after the last search result: any text before it is the
    model announcing the search, not the answer."""
    last = max((i for i, block in enumerate(content)
                if block.type == "web_search_tool_result"), default=-1)
    return content[last + 1:]


def _without_fast(extras):
    """The same request extras minus fast mode (speed and its beta header)."""
    extras = dict(extras)
    extras["extra_body"] = {k: v for k, v in extras["extra_body"].items() if k != "speed"}
    extras.pop("extra_headers", None)
    return extras


def ask(question, history, model_key):
    """Send question (with prior turns) to Claude, return the answer text.

    history is a list of {"role": ..., "content": ...} dicts.
    Returns "" if Claude produced no text.
    Raises anthropic.APITimeoutError / anthropic.APIError on failure.
    """
    model_id = settings.MODELS.get(model_key, settings.MODELS[settings.DEFAULT_MODEL])
    messages = list(history) + [{"role": "user", "content": question}]

    extras = settings.MODEL_REQUEST_EXTRAS.get(model_key, {})
    request = dict(model=model_id, max_tokens=settings.MAX_TOKENS,
                   system=settings.SYSTEM_PROMPT, messages=messages)
    if settings.WEB_SEARCH_TOOL:
        request["tools"] = [settings.WEB_SEARCH_TOOL]
    started = time.monotonic()
    try:
        response = _get_client().messages.create(**dict(request, **extras))
    except anthropic.RateLimitError:
        # Fast mode has its own, smaller capacity: fall back to standard speed.
        if "speed" not in extras.get("extra_body", {}):
            raise
        response = _get_client().messages.create(**dict(request, **_without_fast(extras)))

    usage = getattr(response, "usage", None)
    tool_use = getattr(usage, "server_tool_use", None)
    logger.info("Claude answered in %.1f s (model=%s, speed=%s, searches=%s, in=%s, out=%s)",
                time.monotonic() - started, model_key, getattr(usage, "speed", None),
                getattr(tool_use, "web_search_requests", 0) if tool_use else 0,
                getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None))
    text = "".join(block.text for block in _answer_blocks(response.content)
                   if block.type == "text").strip()
    if response.stop_reason == "max_tokens":
        text = _drop_unfinished_sentence(text)
    return text
