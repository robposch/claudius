"""Claudius configuration -- the one place to customize the skill.

Everything the Lambda reads at runtime lives here. The API key does NOT: it
lives only in hosted/lambda/config.py, which scripts/deploy.sh generates from
config.example.py. Invocation names live in the interaction models
(skill-package/), read by Alexa's build, not the Lambda: keep PERSONA_NAMES
below in sync with them (tests/test_settings.py checks this).

The hosted Lambda runtime is Python 3.8: keep this file, and everything else
in lambda/, 3.8-compatible.
"""

# --- Persona -------------------------------------------------------------
# Spoken name per locale (greeting). MUST match the invocationName in each
# skill-package/interactionModels/custom/<locale>.json.
PERSONA_NAMES = {
    "de-DE": "Claudius", "en-US": "Claudius", "en-GB": "Clauda", "fr-FR": "Clauda",
}
DEFAULT_PERSONA_NAME = "Claudius"   # greeting in a locale not listed above

SYSTEM_PROMPT = (
    "You are answering through a voice assistant (Amazon Alexa). "
    "Reply in one to three short spoken sentences. "
    "Plain text only: no markdown, no lists, no code, no URLs. "
    "Answer in the language of the question."
)

# --- Models --------------------------------------------------------------
MODELS = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-5",
    "opus": "claude-opus-4-8",
}
DEFAULT_MODEL = "haiku"
FAST_MODELS = frozenset({"haiku"})   # skip the spoken "Moment" filler
MODEL_SPOKEN_NAMES = {"haiku": "Haiku", "sonnet": "Sonnet", "opus": "Opus"}
# Words heard for a voice model switch (plus common Alexa mishears) -> MODELS key.
MODEL_WORDS = {
    "haiku": "haiku", "heiku": "haiku",
    "sonnet": "sonnet", "sonett": "sonnet",
    "opus": "opus", "opos": "opus",
}
# A model switch is "<verb> [up to two filler words] <model word>" as the whole
# utterance, e.g. "benutze opus", "wechsle zu sonnet", "use haiku".
SWITCH_VERBS = (
    "benutze", "benutz", "verwende", "nutze", "nimm", "wechsle", "wechsele",
    "modell", "sprachmodell",                   # de
    "use", "switch", "change",                  # en
    "utilise", "prends", "passe",               # fr
)
# Extra Messages API arguments per model, tuned for Alexa's ~8 s window. These
# are model-specific: when you point a key at a different model ID, check the
# API reference for what that model accepts (some reject a disabled-thinking
# or effort setting) and adjust or drop its entry. A model without an entry
# gets a plain request.
# output_config goes through extra_body because the hosted runtime's Python 3.8
# caps the anthropic SDK at 0.72.0, where it is not yet a typed parameter.
MODEL_REQUEST_EXTRAS = {
    # Sonnet 5 thinks adaptively by default; switch that off for latency.
    "sonnet": {"thinking": {"type": "disabled"},
               "extra_body": {"output_config": {"effort": "low"}}},
    # Opus 4.8 does not think unless asked to.
    "opus": {"extra_body": {"output_config": {"effort": "low"}}},
    # Haiku 4.5: no entry, it supports neither setting.
}

# --- Answer behavior -----------------------------------------------------
MAX_TOKENS = 500          # spoken answers stay short
# Alexa abandons the session after ~8 s. This is the SDK's per-request network
# timeout (no retries), not a hard wall-clock deadline for the whole turn.
TIMEOUT_SECONDS = 6.5
HISTORY_TURNS = 8         # user/assistant turn pairs kept as context

# --- Conversation log (optional; off by default -- logs your Q&A text) ---
# When on, every question and answer is written in full to CloudWatch, and
# also POSTed to LOG_WEBHOOK_URL if that is set. The POST carries no
# authentication, so use an https URL that is itself hard to guess. It runs
# before the answer is spoken and can delay it by up to half a second.
LOG_CONVERSATIONS = False
LOG_WEBHOOK_URL = None     # https only, e.g. a Sheet / Notion / server hook

# --- Spoken UI strings (per language) ------------------------------------
STRINGS = {
    "de": {
        "welcome": "Hier ist {name}, dein Draht zu Claude. Was möchtest du wissen?",
        "reprompt": "Frag einfach weiter, oder sag Alexa, stopp.",
        "thinking": "Moment.",
        "timeout": "Das hat zu lange gedauert. Frag bitte noch einmal, oder sage: benutze Haiku.",
        "error": "Da ist etwas schiefgelaufen. Versuch es bitte noch einmal.",
        "goodbye": "Bis bald!",
        "help": ("Stell mir einfach eine Frage. Du kannst auch das Modell wechseln, "
                 "sage zum Beispiel: benutze Opus. Was möchtest du wissen?"),
        "fallback": "Das habe ich nicht verstanden. Was möchtest du wissen?",
        "model_set": "Alles klar, ich benutze jetzt {model}. Was möchtest du wissen?",
    },
    "en": {
        "welcome": "This is {name}, your line to Claude. What would you like to know?",
        "reprompt": "Just ask your next question, or say Alexa, stop when you're done.",
        "thinking": "One moment.",
        "timeout": "That took too long. Please ask again, or say: use Haiku.",
        "error": "Something went wrong. Please try again.",
        "goodbye": "Goodbye!",
        "help": ("Just ask me a question. You can also switch the model, "
                 "for example say: use Opus. What would you like to know?"),
        "fallback": "I did not catch that. What would you like to know?",
        "model_set": "Okay, I will use {model} from now on. What would you like to know?",
    },
    "fr": {
        "welcome": "Ici {name}, ton accès à Claude. Que veux-tu savoir ?",
        "reprompt": "Pose ta prochaine question, ou dis Alexa, stop pour terminer.",
        "thinking": "Un instant.",
        "timeout": "Cela a pris trop de temps. Repose ta question, ou dis : utilise Haiku.",
        "error": "Quelque chose s'est mal passé. Réessaie, s'il te plaît.",
        "goodbye": "À bientôt !",
        "help": ("Pose-moi simplement une question. Tu peux aussi changer de modèle, "
                 "dis par exemple : utilise Opus. Que veux-tu savoir ?"),
        "fallback": "Je n'ai pas compris. Que veux-tu savoir ?",
        "model_set": "D'accord, j'utilise maintenant {model}. Que veux-tu savoir ?",
    },
}

# --- Closing phrases (whole-utterance match ends the session) ------------
STOP_PHRASES = (
    # de
    "stopp", "stop", "halt", "aus", "beenden", "beende", "schluss", "ende",
    "abbrechen", "abbruch", "danke", "danke schön", "vielen dank", "das wars",
    "das war es", "das war's", "das reicht", "das genügt", "tschüss", "tschüs",
    "auf wiedersehen", "fertig", "ich bin fertig", "nein danke", "das ist alles",
    "genug", "danke das wars", "danke das war's", "danke das reicht", "alles klar danke",
    # en
    "cancel", "quit", "exit", "done", "i'm done", "im done", "that's all", "thats all",
    "thank you", "thanks", "thanks that's all", "no thanks", "no thank you", "goodbye",
    "bye", "enough", "that's it", "thats it", "nothing else", "we're done", "that is all",
    # fr
    "arrête", "arrete", "arrêter", "annuler", "quitter", "terminé", "termine",
    "c'est tout", "cest tout", "merci", "au revoir", "fini", "non merci", "ça suffit",
    "ca suffit", "c'est bon", "cest bon", "merci c'est tout",
    # bare negatives -- a "no" in reply to anything should close, not reach Claude
    "nein", "nein danke schön", "nö", "nee", "no", "nope", "non",
    # dismissals / "never mind" -- said when the user has disengaged
    "egal", "ach egal", "ist egal", "ist mir egal", "vergiss es", "vergiss",
    "schon gut", "lass gut sein", "lass mal", "lass es", "nichts", "ach nichts",
    "passt", "passt schon", "ist gut", "ist gut so", "kein bedarf",
    "never mind", "nevermind", "forget it", "forget about it", "nothing",
    "no worries", "leave it",
    "laisse tomber", "rien", "oublie", "oublie ça", "c'est rien", "laisse",
)


def validate():
    """Fail fast with a clear message on a misconfiguration."""
    if DEFAULT_MODEL not in MODELS:
        raise ValueError(
            "DEFAULT_MODEL %r not in MODELS %s" % (DEFAULT_MODEL, sorted(MODELS)))
    for key in FAST_MODELS:
        if key not in MODELS:
            raise ValueError(
                "FAST_MODELS entry %r not in MODELS %s" % (key, sorted(MODELS)))
    for key in MODELS:
        if key not in MODEL_SPOKEN_NAMES:
            raise ValueError("MODEL_SPOKEN_NAMES missing %r" % key)
    for word, key in MODEL_WORDS.items():
        if key not in MODELS:
            raise ValueError(
                "MODEL_WORDS entry %r -> %r not in MODELS %s"
                % (word, key, sorted(MODELS)))
    for key in MODEL_REQUEST_EXTRAS:
        if key not in MODELS:
            raise ValueError(
                "MODEL_REQUEST_EXTRAS entry %r not in MODELS %s" % (key, sorted(MODELS)))
    if not SWITCH_VERBS:
        raise ValueError("SWITCH_VERBS must not be empty")
    if MAX_TOKENS <= 0:
        raise ValueError("MAX_TOKENS must be > 0, got %r" % MAX_TOKENS)
    if TIMEOUT_SECONDS <= 0:
        raise ValueError("TIMEOUT_SECONDS must be > 0, got %r" % TIMEOUT_SECONDS)
    if HISTORY_TURNS < 1:
        raise ValueError("HISTORY_TURNS must be >= 1, got %r" % HISTORY_TURNS)
    langs = set(loc.split("-")[0] for loc in PERSONA_NAMES)
    missing = langs - set(STRINGS)
    if missing:
        raise ValueError("STRINGS missing languages: %s" % sorted(missing))
    if LOG_WEBHOOK_URL is not None and not str(LOG_WEBHOOK_URL).startswith("https://"):
        raise ValueError("LOG_WEBHOOK_URL must be an https:// URL or None")
