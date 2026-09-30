# Customizing

`lambda/settings.py` is the one place to customize how the skill behaves.
`settings.validate()` runs when the Lambda starts and fails with a clear
message on a bad value; the test suite runs it too.

The API key is not in `settings.py`: `scripts/deploy.sh` generates
`hosted/lambda/config.py` from `lambda/config.example.py`, and that file holds
nothing but `ANTHROPIC_API_KEY`. Replace the key with
`scripts/deploy.sh --set-key`.

| Change | Where |
|---|---|
| Models / default model | `lambda/settings.py` (`MODELS`, `DEFAULT_MODEL`, `FAST_MODELS`, `MODEL_SPOKEN_NAMES`). When you change a model ID, also revisit its entry in `MODEL_REQUEST_EXTRAS` (thinking / effort arguments): these are model-specific, and a model that does not accept them answers every question with an API error. |
| Voice model switching | `lambda/settings.py`: `MODEL_WORDS` (spoken model names plus common mishears) and `SWITCH_VERBS` ("use", "benutze", ...). Parsed in code (`detect_model_switch` in `lambda/lambda_function.py`), not by an interaction-model intent. |
| Closing phrases ("danke", "das war's", ...) | `STOP_PHRASES` in `lambda/settings.py`. Because the query slot is elicited, "stopp" lands in the slot instead of firing AMAZON.StopIntent, so closings are matched in code (whole utterance only) and end the session. "Alexa, stopp" with the wake word still fires StopIntent normally. |
| Answer style / system prompt | `lambda/settings.py` (`SYSTEM_PROMPT`) |
| Spoken UI strings | `lambda/settings.py` (`STRINGS`) |
| Timeout / answer length / memory | `lambda/settings.py` (`TIMEOUT_SECONDS`, `MAX_TOKENS`, `HISTORY_TURNS`) |
| Persona name (greeting) | `lambda/settings.py` (`PERSONA_NAMES`, plus `DEFAULT_PERSONA_NAME` for unlisted locales). **Must match the `invocationName` in each `skill-package/interactionModels/custom/<locale>.json`**: the Lambda speaks whatever is in `PERSONA_NAMES`, Alexa recognizes only what is in the interaction model, so a mismatch means the skill introduces itself by a name your device can't invoke. A test (`tests/test_settings.py`) fails on a mismatch. |
| Invocation name | `invocationName` in every interaction model, plus the `examplePhrases` in `skill-package/skill.json` (lowercase; one word is fine for personal skills, store certification would require two). Currently "claudius" (de-DE, en-US) and "clauda" (en-GB, fr-FR): per-locale names are allowed and necessary here, see "Launch phrase routes to a different skill" in [troubleshooting.md](troubleshooting.md). Avoid famous names, re-test every locale (simulator and real device) after renaming, and keep `PERSONA_NAMES` in sync (row above). |
| Name shown in the Alexa app | `name` per locale in `skill-package/skill.json` ("Claudius (unofficial)"). Do not name it "Claude": that presents the skill as Anthropic's product. |
| Add a locale | New `skill-package/interactionModels/custom/<locale>.json` (copy en-US, translate the samples), add the locale to `skill-package/skill.json`, and add a `STRINGS` entry and a `PERSONA_NAMES` entry in `lambda/settings.py`. |
| Conversation log | `lambda/settings.py` (`LOG_CONVERSATIONS`, `LOG_WEBHOOK_URL`). Off by default. When on, each question and answer is logged in full to CloudWatch; if `LOG_WEBHOOK_URL` (https only) is also set, the same payload is POSTed there, unauthenticated. A failed webhook call is logged and swallowed and never breaks the answer, but the POST is synchronous: a slow webhook delays the spoken answer by up to 0.5 s. This records everything said to the skill, so tell the people who use it. |

## After a change

```sh
.venv/bin/pytest           # settings validation, handlers, Claude client, log, deploy helpers
.venv/bin/ruff check .     # lint
scripts/deploy.sh          # runs the tests again, then deploys
ask dialog --locale en-US  # check it in the simulator
```

Code under `lambda/` has to stay compatible with **Python 3.8**, the
Alexa-hosted runtime. If you changed how responses are built or touched the
interaction models, test on a real Echo as well: the simulator accepts
directives that devices reject.
