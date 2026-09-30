"""Thin wrapper around the Anthropic Messages API for voice-length answers."""

import re

import anthropic

import config
import settings

_client = None

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


def ask(question, history, model_key):
    """Send question (with prior turns) to Claude, return the answer text.

    history is a list of {"role": ..., "content": ...} dicts.
    Returns "" if Claude produced no text.
    Raises anthropic.APITimeoutError / anthropic.APIError on failure.
    """
    model_id = settings.MODELS.get(model_key, settings.MODELS[settings.DEFAULT_MODEL])
    messages = list(history) + [{"role": "user", "content": question}]

    response = _get_client().messages.create(
        model=model_id,
        max_tokens=settings.MAX_TOKENS,
        system=settings.SYSTEM_PROMPT,
        messages=messages,
        **settings.MODEL_REQUEST_EXTRAS.get(model_key, {}),
    )

    text = "".join(
        block.text for block in response.content if block.type == "text"
    ).strip()
    if response.stop_reason == "max_tokens":
        text = _drop_unfinished_sentence(text)
    return text
