# Claudius

**Talk to Claude through your Amazon Echo.** An Alexa custom skill that
forwards your spoken questions to the Claude API and reads the answer back,
with multi-turn conversations and voice-switchable models.

```
"Alexa, open claudius"
"why is the sky blue"
"and why are sunsets red"        <- follow-ups keep context
"use opus"                       <- switch model by voice
```

No audio code anywhere: Alexa does speech-to-text before your backend runs and
text-to-speech after it returns. The backend is a small Python Lambda, hosted
for free as an Alexa-hosted skill (no AWS account needed).

About the name: you call the skill **"claudius"** ("clauda" in UK English and
French) because Alexa will not route the word "claude" to a custom skill; see
[Limitations](#limitations). In the Alexa app it shows up as
"Claudius (unofficial)". This is a personal project, not an Anthropic or
Amazon product.

## Features

- **Multi-turn chat**: the session stays open, follow-up questions carry the
  conversation history (last 8 turns).
- **Model switching by voice**: Haiku 4.5 by default (fastest, fits Alexa's
  ~8 second response window), "use sonnet" / "use opus" switches, and the
  choice persists across sessions.
- **Four locales**: de-DE, en-US, en-GB, fr-FR. Claude answers in the
  language you ask in.
- **Graceful latency handling**: on the slower models a brief "Moment" plays
  while Claude thinks (skipped on the fast default, Haiku, which answers
  well inside the window); a hard client timeout gives a spoken retry hint
  instead of a dead session.
- **Free hosting**: Alexa-hosted skill (managed Lambda + DynamoDB within the
  AWS free tier).

## Requirements

- Amazon account with Echo device(s), plus a free
  [developer account](https://developer.amazon.com) on the same login
- git, Python 3 (3.8 or newer) and Node.js
- An [Anthropic API key](https://platform.claude.com/). Create a dedicated
  one for this skill and give it a spend limit: hosting is free, but every
  question is billed to that key, and anyone within earshot of your Echo can
  ask questions or switch to a more expensive model.

## Setup

About 15 minutes, once. Run everything from the root of your clone.

### 1. Log in to Amazon

```sh
npm install -g ask-cli
ask configure
```

A browser opens. Sign in with the **same Amazon account your Echo is
registered to**; a developer account is created for you if you have none.
When the CLI asks "Link AWS account?", answer **No**: an Alexa-hosted skill
needs no AWS account.

### 2. Create the hosted skill

```sh
ask new
```

| Prompt | Answer |
|---|---|
| Choose a modeling stack | Interaction Model (older CLIs call it "Custom") |
| Programming language | Python |
| Hosting method | Alexa-hosted skills |
| Default region | the one closest to you (e.g. eu-west-1 for Europe) |
| Skill name | claudius |
| Folder name | hosted |

Amazon provisions a free Lambda and DynamoDB table and clones the skill's own
private git repo into `./hosted`. That folder is gitignored here and will hold
your API key: never commit or publish it.

The first time you create a hosted skill, the CLI sends you to a CAPTCHA page
in the browser before it continues.

### 3. Deploy

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
export ANTHROPIC_API_KEY=sk-ant-...   # first deploy only; or let the script prompt you
scripts/deploy.sh
```

The script runs the tests, pushes the Lambda code to the hosted repo (the
push is the deployment) and waits for the build, applies the skill manifest
and interaction models, and enables the skill for your account. It takes a
few minutes. Re-run it after every change. It only takes the key on the
first deploy: after that `ANTHROPIC_API_KEY` is ignored, so a general-purpose
key in your shell never overwrites the skill's own.

| Command | What it does |
|---|---|
| `scripts/deploy.sh --check` | verifies your setup, deploys nothing |
| `scripts/deploy.sh --set-key` | replaces the API key of the deployed skill |
| `scripts/deploy.sh --skip-tests` | deploys without running the tests |
| `scripts/deploy.sh --help` | lists everything |

### 4. Try it

```sh
ask dialog --locale en-US    # a text simulator; type: open claudius
```

Then on your Echo: **"Alexa, open claudius"**.

### If `ask configure` or `ask new` hangs

Both wait for a browser redirect to `localhost:9090`. Corporate firewalls and
proxies often block it, and the CLI then hangs although the browser reported
success. Press Ctrl+C and take the route that needs no redirect:

1. Log in with `ask configure --no-browser`. It prints a URL; open it, sign
   in, and paste the code shown on the page back into the terminal.
2. Create the skill in the
   [developer console](https://developer.amazon.com/alexa/console/ask)
   instead of with `ask new`: **Create Skill**, name `claudius`, any of the
   four locales as primary (the deploy adds the rest), type of experience
   **Other**, model **Custom**, sync locales **Disabled**, hosting service
   **Alexa-hosted (Python)**, the hosting region closest to you, template
   **Start from Scratch**.
3. Copy the skill ID from the console's skill list ("Copy Skill ID") and link
   the skill:

   ```sh
   ask init --hosted-skill-id <skill-id>   # folder name: hosted
   ```

Continue with step 3. `ask init` is also how you link an existing skill on
another machine.

## Talking to it

Getting in (wake word required):

```
"Alexa, open claudius"                        <- opens a conversation
"Alexa, ask claudius what is a comet"         <- one-shot: asks and stays open
```

(German: "öffne claudius" / "frage claudius ...". UK English and French use
the invocation "clauda": "open clauda" / "ouvre clauda".)

Inside the session the microphone reopens for ~8 seconds after every answer
(blue ring) — no wake word, no prefix. Just talk; the whole utterance is
captured as your question (the skill elicits a free-form slot, so you never
need a carrier word):

| You say | What happens |
|---|---|
| Any question — "how do rainbows form", "who was Einstein", "und wo leben Elefanten" | Goes to Claude as your question |
| "use opus" / "use sonnet" / "use haiku" (de: "benutze opus") | Switches the model; the choice persists across sessions |
| "help" | Explains the skill |
| "stop" — or a natural closing: "danke", "das war's", "fertig", "tschüss" (en: "thanks", "that's all", "done"; fr: "merci", "c'est tout") | Ends the session and stops the mic |

You can also say **"Alexa, stopp"** (with the wake word) at any time to close
it immediately. Closing phrases are matched only when they are the whole
utterance, so "was ist ein Stoppschild" or "was heißt danke auf Englisch"
are still answered as questions.

Follow-ups keep context (the last 8 question/answer pairs), so pronouns work:
"Who was Einstein?" → "When did he die?". Model switching is detected from
what you say, so a question that merely mentions a model ("what is opus") is
still answered, not treated as a switch.

If you stay silent, Alexa reprompts once after ~8 seconds, waits again, then
closes the session quietly — after that you're back to "Alexa, open claudius".

## Customizing

Everything worth tuning in the backend lives in one file,
`lambda/settings.py`: persona name, models, system prompt, spoken strings,
closing phrases, timeout, answer length, conversation log. Invocation names
and locales live in `skill-package/`.

[docs/customizing.md](docs/customizing.md) lists what to change where. After
a change, run `.venv/bin/pytest`, then `scripts/deploy.sh`.

## Troubleshooting

The usual suspects:

| Symptom | Fix |
|---|---|
| `ask configure` / `ask new` hangs after the browser login | A firewall blocks the redirect; see [above](#if-ask-configure-or-ask-new-hangs). |
| The skill opens, but every answer is "Something went wrong" | Almost always the API key. Replace it with `scripts/deploy.sh --set-key`. |
| "That took too long" on every question | The model is too slow for Alexa's 8 second window. Say "use haiku". |
| "Alexa, open claudius" opens something else, or nothing | Your Echo's language is not one of the four locales, or Alexa misheard the name. |

Everything else, with causes and fixes: [docs/troubleshooting.md](docs/troubleshooting.md).

## Security and privacy

- **Where your words go.** Alexa transcribes what you say; the skill sends
  that text, plus up to the last 8 question/answer pairs of the session, to
  the Anthropic API. Nothing else is stored: the history lives in the Alexa
  session and is gone when it ends. Only your model choice is persisted.
- **Amazon's side.** Alexa keeps its own voice history of what it heard,
  as it does for every skill; manage it in the Alexa app.
- **Logs.** By default the Lambda logs errors and the model used, not what
  you said. Setting `LOG_CONVERSATIONS = True` writes every question and
  answer in full to CloudWatch, and `LOG_WEBHOOK_URL` additionally POSTs them,
  without authentication, to an https URL of your choice. Leave both off
  unless you want a transcript, and tell the people you live with.
- **The API key.** It exists only in `hosted/lambda/config.py`, inside the
  hosted skill's private repo on Amazon's side and your local clone of it.
  Never commit `hosted/` anywhere else. Rotate the key with
  `scripts/deploy.sh --set-key`.
- **No access control.** Whoever can talk to your Echo can use the skill, at
  your expense. A spend limit on the key is the only cap.
- **Reporting a vulnerability.** Please use GitHub's private vulnerability
  reporting on this repository rather than a public issue.

## How it works

```
Echo device
  -> Alexa speech-to-text (built in)
  -> Custom skill (invocation "claudius" or "clauda", per locale)
  -> Alexa-hosted Lambda (Python, ASK SDK)
       progressive response, then Claude API call
       session attributes: conversation history
       DynamoDB: persisted model choice
  -> answer + re-opened microphone (query-slot elicitation)
  -> Alexa text-to-speech (built in)
```

Two Alexa quirks this design absorbs:

- **~8 second response limit.** Alexa abandons the session if the skill is
  slow. Hence Haiku by default, `max_tokens=500`, thinking disabled / effort
  low on the bigger models, a 6.5 s client timeout, and a progressive
  "Moment" response while waiting — sent only on the slower models
  (`FAST_MODELS` in `lambda/settings.py`), since Haiku needs no filler.
- **Free-form speech capture.** Alexa's `AMAZON.SearchQuery` slot can't stand
  alone, so after each turn the skill elicits it (`Dialog.ElicitSlot`) and the
  entire next utterance lands in the slot — no carrier phrase, no competing
  intent. This requires a **dialog model** declaring the slot in each
  interaction model; without it, real devices reject the directive with
  "Invalid Directive" and the turn dies silently (the simulator does not
  enforce this, so the dialog model must be device-tested). Model switching
  ("benutze opus") is parsed from the captured text in the Lambda rather than
  a separate intent, which otherwise misroutes ordinary questions into it.

The deploy goes through two channels on purpose. Lambda code is pushed to the
hosted repo with git. The manifest and interaction models are applied through
Amazon's skill management API instead, because the hosted git pipeline only
processes files changed in the pushed commit, saves interaction models
without building them, and wipes the Lambda endpoint when it imports
`skill.json`.

## Project layout

```
skill-package/            manifest + interaction models (per locale)
lambda/                   the skill backend
  lambda_function.py      ASK SDK request handlers
  claude_client.py        the Anthropic API call
  settings.py             the one place to customize behavior (persona,
                          models, prompt, strings, timeouts, log toggle)
  conversation_log.py     optional Q&A history (CloudWatch + webhook)
  config.example.py       template; deploy.sh generates the hosted
                          config.py (API key only) from it
tests/                    pytest suite: settings, handlers, Claude client,
                          conversation log, deploy helpers
scripts/deploy.sh         runs the tests, then lambda push + build wait,
                          manifest/models via SMAPI
scripts/deploy_helpers.py the file-handling steps of deploy.sh, testable
docs/                     customizing and troubleshooting references
pyproject.toml            pytest and ruff configuration
.github/workflows/ci.yml  tests (Python 3.8 and 3.12), ruff, shellcheck
AGENTS.md, CLAUDE.md      instructions for AI coding agents working in this repo
hosted/                   created by `ask new` or `ask init`; private, gitignored
```

## Contributing

Issues and pull requests are welcome. Before you open a PR:

- Run `.venv/bin/pytest` and `.venv/bin/ruff check .`; CI runs both, plus
  shellcheck.
- Keep everything under `lambda/` compatible with **Python 3.8**, the
  Alexa-hosted runtime (CI tests on 3.8).
- If you change how responses are built or touch the interaction models, test
  on a real Echo. The simulator accepts directives that devices reject.

## Limitations

- Answers are capped short; this is a voice assistant, not a research tool.
- The invocation name is "claudius" (de-DE, en-US) / "clauda" (en-GB, fr-FR),
  not "claude": Alexa hands "claude" to another skill, so it never reaches
  yours. Invented words fail elsewhere: German devices transcribe "clauda"
  as "Claudia" (and treat it as a device name), while French NLU accepts
  only "clauda". If you rename, test each locale in the simulator AND on a
  real device; the Alexa app's voice history shows what was actually heard.
- Opus on hard questions can exceed the timeout (you get a spoken retry hint;
  say "use haiku" for speed).
- The API key lives in the hosted skill's private repo (`hosted/lambda/config.py`),
  because Alexa-hosted Lambdas have no environment variables. Fine for
  personal use; use your own Lambda + a secrets manager if you need better.
- With the conversation log's webhook enabled, a slow webhook delays the
  spoken answer by up to half a second.
- Personal / development use. Publishing to the skill store would need a
  two-word invocation name and certification review.

## Disclaimer

Unofficial, personal project. Not affiliated with, endorsed by, or sponsored
by Anthropic or Amazon. "Claude" is a trademark of Anthropic; "Alexa" and
"Echo" are trademarks of Amazon.

## License

MIT, see [LICENSE](LICENSE).
