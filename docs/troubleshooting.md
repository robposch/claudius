# Troubleshooting

Runtime logs are in the Alexa Developer Console: your skill -> Code tab ->
CloudWatch link. The Alexa app's voice history shows what Alexa actually
heard. Your skill ID is in `hosted/.ask/ask-states.json` and in the console's
skill list.

"Setup" below means the [Setup section of the README](../README.md#setup).

## During setup

| Symptom | Cause / fix |
|---|---|
| `ask configure` / `ask new` hangs at "Listening on http://localhost:9090" | A firewall or proxy blocks the OAuth or CAPTCHA callback. Use the route without a redirect: [If `ask configure` or `ask new` hangs](../README.md#if-ask-configure-or-ask-new-hangs). |
| Wizard dies with `Error: readline was closed` | It was run in a shell without a terminal (a coding agent's shell, a script, CI). Run it in a real terminal. |
| `ask new` fails with "Can't resolve profile [default]" | The login (Setup step 1) was skipped or aborted before finishing. Run `ask configure` (or `ask configure --no-browser`) first. |
| You said yes to "Link AWS account" and landed on an AWS sign-in page | Not needed for Alexa-hosted skills. Close the tab, Ctrl+C the CLI, re-run `ask configure`, answer No. |

## During deploy

| Symptom | Cause / fix |
|---|---|
| Deploy stops with "The tests cannot run" | pytest is not installed for the interpreter the script uses. Install the dev dependencies into `.venv` (Setup step 3), or pass `--skip-tests`. |
| A SMAPI step fails | The script prints the failing `ask smapi ...` command and its output. An expired login is fixed by re-running `ask configure`. |
| Build FAILED after push | `ask smapi get-skill-status -s <skill-id>` shows which part. Interaction-model errors are usually malformed samples; Lambda errors show in CloudWatch. |
| `hostedSkillDeployment` FAILED right after push | Almost always pip resolution in `lambda/requirements.txt`. The hosted runtime is **Python 3.8** (`ask smapi get-alexa-hosted-skill-metadata -s <skill-id>`), which caps `anthropic` at 0.72.0 and means every requirement needs a release that still supports 3.8. Reproduce locally: `pip download -r lambda/requirements.txt --python-version 38 --platform manylinux2014_x86_64 --only-binary=:all: -d /tmp/x`. (One past failure: `ask-sdk-s3-persistence-adapter>=1.19.0`, of which only 1.0.0 exists.) |
| Deploy stops with "The live skill manifest has no Lambda endpoint to carry over", or the skill answers "No endpoint was found for the specified region" | The manifest lost its Lambda endpoint (a raw `skill.json` import, or `update-skill-manifest` without an `apis` section), or the live manifest could not be fetched (the script prints why). `scripts/deploy.sh` carries the live `apis` section over and refuses to upload a manifest without an endpoint. To repair a manifest that already lost it: `ask smapi update-skill-manifest` with the endpoint ARN from an earlier `get-skill-manifest` (both the default `endpoint` and `regions.EU` / `NA`). |

## In the simulator

| Symptom | Cause / fix |
|---|---|
| English one-shot simulations fail with a bare "An unexpected error occurred" | Simulator quirk with `AMAZON.SearchQuery` one-shots (launch and de-DE one-shots pass, and the Lambda answers fine via `ask smapi invoke-skill`). The in-session flow is unaffected; verify on a device. |

## On the device

| Symptom | Cause / fix |
|---|---|
| Skill not invocable on the device | The device's language is not one of de-DE / en-US / en-GB / fr-FR, or Development testing is not enabled (Developer Console -> Test -> Development). |
| Launch phrase routes to a different skill, a device, or nothing | Invocation names are a minefield, locale by locale. "claude" is captured by another skill everywhere. Invented words pass the text simulator but fail real speech: German devices transcribe "clauda" as "Claudia" and then treat it as a smart-home device name ("kann kein Gerät namens Claudia finden"). French NLU accepts "clauda" but rejects "aclauda" and "claudius"; the en-GB simulator rejects "claudius". Hence per-locale names: "claudius" (de-DE, en-US), "clauda" (en-GB, fr-FR). When renaming, test every locale with `ask smapi simulate-skill` AND on a real device: the simulator bypasses speech recognition. |
| Skill opens but every answer is the error message | Almost always the API key. Check CloudWatch for a 401, then replace the key with `scripts/deploy.sh --set-key`. A model that rejects its `MODEL_REQUEST_EXTRAS` shows up the same way, as a 400. |
| "That took too long" on every question | The model is too slow for the 8 s window. Say "use haiku", or raise `TIMEOUT_SECONDS` in `lambda/settings.py` slightly (max ~7). |
| One-shot "ask claudius X" is misheard | One-shot capture depends on the carrier samples on AskClaudeIntent and on Alexa's speech recognition. In-session it does not matter: the query slot is elicited, so any phrasing is captured. Prefer opening first ("open claudius"), then talking. |
| Greeting plays, then silence after the question; the Alexa app shows "Invalid Directive: Dialog.ElicitSlot" (CloudWatch: "Session ended with error") | The interaction model is missing a **dialog model** for the elicited slot. `Dialog.ElicitSlot` is only valid when the slot is declared under `interactionModel.dialog` (with `elicitationRequired: true` and a `prompts` entry); without it, real devices reject the directive and the turn dies after the answer. The text simulator does NOT enforce this. Each locale here declares that dialog model: keep it if you touch the interaction models. |
| A normal question is answered with "that model is unknown" or treated as a model switch | A separate model-switch **intent** with a permissive slot over-matches questions on the device. This skill has no such intent: "benutze/use opus" is parsed from the elicited query text in `lambda/lambda_function.py` (`detect_model_switch`). Do not add a model-switch intent to the interaction model. |
| Model switch does not persist across sessions | Persistence environment variables are missing (rare on hosted skills). CloudWatch shows "No persistence adapter configured". Switching within a session still works. |
