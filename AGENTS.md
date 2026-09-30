# Agent instructions

You are a coding agent working in this repository: an Alexa custom skill that
forwards spoken questions to the Claude API and speaks the answer.

The facts live in the human documentation. Read it; do not work from memory:

- [README.md](README.md): what the skill does, **Setup** (the exact commands
  and wizard answers), how it works, project layout.
- [docs/customizing.md](docs/customizing.md): what to change where.
- [docs/troubleshooting.md](docs/troubleshooting.md): symptoms, causes, fixes.

This file only covers what is different for you as an agent.

## Rules

1. **The API key never enters this repo or the chat.** It belongs only in
   `hosted/lambda/config.py`. Never ask the user to paste it into the
   conversation: they export `ANTHROPIC_API_KEY` in the shell that runs
   `scripts/deploy.sh`, or the script prompts them with hidden input.
   Replacing it later: `scripts/deploy.sh --set-key`.
2. **`hosted/` is a separate, private git repo** holding the deployed key and
   the skill ID. It is gitignored here. Never add it to this repo, never
   publish it, and do not read or edit files inside it, `config.py` included.
   Edit the sources here and run `scripts/deploy.sh`, which mirrors
   `lambda/*.py` into it and leaves `config.py` alone.
3. **You cannot run the interactive ASK wizards.** `ask configure`, `ask new`
   and `ask init` need a real terminal and die in an agent shell with
   `Error: readline was closed`. Hand them to the user (see below).
4. **Code under `lambda/` must stay Python 3.8-compatible**, syntax and
   dependencies: that is the hosted runtime. Tests and `scripts/` run on any
   Python 3.8 or newer.
5. **Do not deploy `skill-package/` through the hosted git repo**, and do not
   add a model-switch intent to the interaction models. README "How it works"
   explains both.

## Deploying for a user

Start by detecting the state:

```sh
scripts/deploy.sh --check
```

| Finding | What you do |
|---|---|
| ask-cli missing | `npm install -g ask-cli` (you may run this) |
| ask-cli not configured | Hand README Setup step 1 to the user |
| no hosted repo at `./hosted` | Hand README Setup step 2 to the user |
| all checks pass | Deploy (README Setup step 3) |

**Handing a step to the user.** Tell them to run the command in their own
terminal, from the project root, and give them the answers from the README up
front. Warn them about the two pitfalls before they start: answer **No** to
"Link AWS account?", and if the CLI hangs after the browser login, a firewall
is blocking the redirect and the README section "If `ask configure` or
`ask new` hangs" is the way through. On a network you already know to be
locked down, send them down that route directly. If they need the skill ID
for `ask init`, you can look it up: `ask smapi list-skills-for-vendor`.

**Deploying.** You can run README Setup step 3 yourself, except for the key:
if `hosted/lambda/config.py` does not exist yet and `ANTHROPIC_API_KEY` is
not set in your shell, ask the user to run `scripts/deploy.sh` once in their
own terminal so the hidden prompt can take the key. The script is idempotent;
re-run it after any source change.

**Verifying.** Do not stop at a green deploy.

```sh
ask smapi simulate-skill -s <skill-id> -g development \
  --device-locale de-DE --input-content "frage claudius was ist ein schwarzes loch"
```

Use de-DE for this: English one-shot simulations fail with a spurious
simulator error (see troubleshooting). The skill ID is printed by the deploy
script. `ask dialog --locale en-US` is the interactive alternative, for the
user's terminal: "open claudius", a question, a follow-up that needs the
context, "use opus", "stop".

What to expect: Haiku answers well inside 8 s. On Opus a hard question may
hit the 6.5 s client timeout, and the skill must then answer with a spoken
retry hint, never go silent.

The simulator accepts directives that real devices reject. After any change
to how responses are built, or to the interaction models, say so and ask the
user to test on their Echo; you cannot do that part.

## Changing the code

- Find the place in [docs/customizing.md](docs/customizing.md) first. Most
  behavior is a setting in `lambda/settings.py`, not a code change.
- Write or update the test, then the code. Run `.venv/bin/pytest` and
  `.venv/bin/ruff check .` (venv setup: README Setup step 3). CI also runs
  shellcheck on `scripts/deploy.sh`.
- The file-handling parts of the deploy are in `scripts/deploy_helpers.py`,
  with tests. Keep logic that can be tested there rather than in the shell
  script.
- When behavior, options or settings change, update the README and `docs/`
  in the same change. They are the source of truth; this file should not
  restate them.
- After any change: deploy, then verify as above.
