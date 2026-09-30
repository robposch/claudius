#!/usr/bin/env bash
# Claudius deploy: sync the Lambda code into your Alexa-hosted skill repo and
# push (the push deploys the backend), then apply the skill manifest and
# interaction models via SMAPI, and enable Development testing.
#
# Why the manifest and interaction models go through SMAPI instead of git:
# the hosted git pipeline only processes paths changed in the pushed commit,
# it saves interaction models without building them, and importing skill.json
# verbatim wipes the Lambda endpoint Amazon injected at provisioning time.
# SMAPI avoids all three problems (the endpoint is preserved by merging the
# live manifest's apis section).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HELPERS="$ROOT/scripts/deploy_helpers.py"
HOSTED_DIR="${CLAUDIUS_HOSTED_DIR:-$ROOT/hosted}"
CHECK_ONLY=0
SKIP_TESTS=0
SET_KEY=0

usage() {
  cat <<'EOF'
Usage: scripts/deploy.sh [options] [hosted-dir]

  (no options)    deploy: run the tests, push the Lambda code, apply the
                  manifest and interaction models, enable Development testing
  --check         verify prerequisites only, deploy nothing
  --skip-tests    deploy without running the test suite first
  --set-key       replace the Anthropic API key of an already deployed skill
  -h, --help      show this help

hosted-dir is the Alexa-hosted skill's git repo. It defaults to ./hosted, or
to $CLAUDIUS_HOSTED_DIR if that is set.

The Anthropic API key is asked for on the first deploy and with --set-key. It
is read from $ANTHROPIC_API_KEY, or prompted for with hidden input, and is
written only to <hosted-dir>/lambda/config.py (the hosted skill's private
repo), never to this repo.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=1 ;;
    --skip-tests) SKIP_TESTS=1 ;;
    --set-key) SET_KEY=1 ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "deploy.sh: unknown option: $arg (see --help)" >&2; exit 2 ;;
    *) HOSTED_DIR="$arg" ;;
  esac
done

if [ -t 1 ]; then
  C_BLUE=$'\033[1;34m' C_GREEN=$'\033[1;32m' C_YELLOW=$'\033[1;33m'
  C_RED=$'\033[1;31m' C_OFF=$'\033[0m'
else
  C_BLUE="" C_GREEN="" C_YELLOW="" C_RED="" C_OFF=""
fi
say()  { printf '%s==>%s %s\n' "$C_BLUE" "$C_OFF" "$*"; }
ok()   { printf '%s ok %s %s\n' "$C_GREEN" "$C_OFF" "$*"; }
warn() { printf '%swarn%s %s\n' "$C_YELLOW" "$C_OFF" "$*"; }
fail() { printf '%sFAIL%s %s\n' "$C_RED" "$C_OFF" "$*"; }

MISSING=0
need_tool() {
  if command -v "$1" >/dev/null 2>&1; then
    ok "$1 found"
  else
    fail "$1 not found. $2"
    MISSING=1
  fi
}

say "Checking prerequisites"
need_tool git    "Install git first."
need_tool node   "Install Node.js (needed by ask-cli): https://nodejs.org"
need_tool python3 "Install Python 3."
need_tool ask    "Install the ASK CLI: npm install -g ask-cli"

if [ -f "$HOME/.ask/cli_config" ]; then
  ok "ask-cli is configured"
else
  fail "ask-cli is not configured. Run in a terminal (opens a browser login): ask configure"
  MISSING=1
fi

if [ -d "$HOSTED_DIR/.git" ] && [ -d "$HOSTED_DIR/lambda" ]; then
  ok "hosted skill repo found at $HOSTED_DIR"
else
  fail "No hosted skill repo at $HOSTED_DIR."
  echo "     Create it once (interactive, ~2 min):"
  echo "       cd $ROOT && ask new"
  echo "       answers: Interaction Model -> Python -> Alexa-hosted -> default region"
  echo "                skill name: claudius   folder name: hosted"
  echo "     Or link an existing hosted skill:"
  echo "       cd $ROOT && ask init --hosted-skill-id <your-skill-id>   # folder name: hosted"
  MISSING=1
fi

if [ "$MISSING" -ne 0 ]; then
  echo
  fail "Prerequisites missing (see above). Fix them and re-run."
  exit 1
fi

if [ "$CHECK_ONLY" -eq 1 ]; then
  echo
  ok "All prerequisites satisfied. Run scripts/deploy.sh to deploy."
  exit 0
fi

if [ "$SKIP_TESTS" -ne 1 ]; then
  # Prefer the project venv; a pytest that merely happens to be on PATH
  # usually lacks the skill's dependencies.
  if [ -x "$ROOT/.venv/bin/python" ]; then
    TEST_PYTHON="$ROOT/.venv/bin/python"
  else
    TEST_PYTHON="python3"
  fi
  if ! "$TEST_PYTHON" -c 'import pytest' >/dev/null 2>&1; then
    fail "The tests cannot run: pytest is not installed for $TEST_PYTHON."
    echo "     Install the dev dependencies once:"
    echo "       cd $ROOT && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt"
    echo "     Or deploy untested: scripts/deploy.sh --skip-tests"
    exit 1
  fi
  say "Running tests"
  if (cd "$ROOT" && "$TEST_PYTHON" -m pytest -q); then
    ok "tests passed"
  else
    fail "tests failed -- aborting deploy (use --skip-tests to override)"
    exit 1
  fi
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# Run a command without its output; if it fails, show what it printed.
quiet() {
  if ! "$@" >"$TMP_DIR/command.log" 2>&1; then
    fail "command failed: $*"
    sed 's/^/     /' "$TMP_DIR/command.log" >&2
    return 1
  fi
}

SKILL_ID="$(python3 "$HELPERS" skill-id "$HOSTED_DIR/.ask/ask-states.json")"
if [ -z "$SKILL_ID" ]; then
  fail "Could not read skill id from $HOSTED_DIR/.ask/ask-states.json."
  exit 1
fi
ok "skill id: $SKILL_ID"

say "Syncing lambda code into $HOSTED_DIR"
# skill-package/ is deliberately NOT synced into the hosted repo (see header).
# Stale copies from early deployments may remain there; they are harmless as
# long as no commit touches them.
REMOVED="$(python3 "$HELPERS" sync-lambda "$ROOT/lambda" "$HOSTED_DIR/lambda")"
ok "lambda files synced"
if [ -n "$REMOVED" ]; then
  warn "removed modules that no longer exist in lambda/: $(echo "$REMOVED" | tr '\n' ' ')"
fi

CONFIG="$HOSTED_DIR/lambda/config.py"
if [ "$SET_KEY" -eq 0 ] && [ -f "$CONFIG" ] && ! grep -q "REPLACE-ME" "$CONFIG"; then
  ok "config.py already present (replace the key with --set-key)"
else
  say "Writing lambda/config.py in the hosted repo"
  KEY="${ANTHROPIC_API_KEY:-}"
  if [ -z "$KEY" ] && [ -t 0 ]; then
    printf 'Paste your Anthropic API key (input hidden): '
    read -rs KEY
    echo
  fi
  if [ -z "$KEY" ]; then
    fail "No API key. Export ANTHROPIC_API_KEY or run interactively."
    exit 1
  fi
  case "$KEY" in
    sk-ant-*) : ;;
    *) warn "Key does not start with sk-ant-, continuing anyway." ;;
  esac
  if ! CLAUDIUS_API_KEY="$KEY" python3 "$HELPERS" write-config \
      "$ROOT/lambda/config.example.py" "$CONFIG"; then
    fail "config.py was not written."
    exit 1
  fi
  ok "config.py written (stays in the hosted skill's private repo only)"
fi

say "Committing and pushing lambda (a git push deploys the hosted Lambda)"
cd "$HOSTED_DIR"
git add -A
NEW_COMMIT=0
if git diff --cached --quiet; then
  ok "nothing new to commit"
else
  git commit -q -m "Deploy Claudius $(date '+%Y-%m-%d %H:%M')"
  NEW_COMMIT=1
fi
git push
ok "pushed"
HEAD_SHA="$(git rev-parse HEAD)"

if [ "$NEW_COMMIT" -eq 1 ]; then
  say "Waiting for the hosted Lambda build of commit ${HEAD_SHA:0:7} (up to ~6 min)"
  STATUS="UNKNOWN"
  for _ in $(seq 1 36); do
    sleep 10
    STATUS="$(ask smapi get-skill-status -s "$SKILL_ID" 2>/dev/null | python3 -c '
import json, sys
head = sys.argv[1]
try:
    d = json.load(sys.stdin)["hostedSkillDeployment"]["lastUpdateRequest"]
except Exception:
    print("UNKNOWN"); raise SystemExit
cid = (d.get("deploymentDetails") or {}).get("commitId", "")
st = d.get("status", "UNKNOWN")
print(st if cid == head else "PENDING")
' "$HEAD_SHA" 2>/dev/null || echo UNKNOWN)"
    case "$STATUS" in
      SUCCEEDED|FAILED) break ;;
      *) printf '.' ;;
    esac
  done
  echo
  case "$STATUS" in
    SUCCEEDED) ok "hosted Lambda build succeeded" ;;
    FAILED)    fail "hosted Lambda build FAILED. Inspect: ask smapi get-skill-status -s $SKILL_ID"; exit 1 ;;
    *)         warn "build still in progress or status unknown. Check: ask smapi get-skill-status -s $SKILL_ID" ;;
  esac
fi

say "Applying skill manifest via SMAPI (preserving the Lambda endpoint)"
if ! ask smapi get-skill-manifest -s "$SKILL_ID" -g development \
    >"$TMP_DIR/live.json" 2>"$TMP_DIR/live.err"; then
  warn "could not fetch the live manifest:"
  sed 's/^/     /' "$TMP_DIR/live.err" >&2
fi
if ! python3 "$HELPERS" merge-manifest "$ROOT/skill-package/skill.json" \
    "$TMP_DIR/live.json" "$TMP_DIR/manifest.json"; then
  fail "manifest not applied (the Lambda code above is already deployed)."
  exit 1
fi
quiet ask smapi update-skill-manifest -s "$SKILL_ID" -g development \
  --manifest "file:$TMP_DIR/manifest.json"
M_STATUS="UNKNOWN"
for _ in $(seq 1 30); do
  M_STATUS="$(ask smapi get-skill-status -s "$SKILL_ID" --resource manifest 2>/dev/null | python3 -c '
import json, sys
print(json.load(sys.stdin)["manifest"]["lastUpdateRequest"]["status"])
' 2>/dev/null || echo UNKNOWN)"
  [ "$M_STATUS" != "IN_PROGRESS" ] && break
  sleep 2
done
if [ "$M_STATUS" = "SUCCEEDED" ]; then
  ok "manifest applied"
else
  fail "manifest update status: $M_STATUS. Inspect: ask smapi get-skill-status -s $SKILL_ID --resource manifest"
  exit 1
fi

say "Applying interaction models via SMAPI"
for f in "$ROOT"/skill-package/interactionModels/custom/*.json; do
  loc="$(basename "$f" .json)"
  quiet ask smapi set-interaction-model -s "$SKILL_ID" -g development -l "$loc" \
    --interaction-model "file:$f"
  ok "submitted $loc"
done
say "Waiting for interaction model builds"
IM_STATUS="UNKNOWN"
for _ in $(seq 1 40); do
  sleep 5
  IM_STATUS="$(ask smapi get-skill-status -s "$SKILL_ID" --resource interactionModel 2>/dev/null | python3 -c '
import json, sys
d = json.load(sys.stdin).get("interactionModel", {})
sts = [v["lastUpdateRequest"]["status"] for v in d.values()]
if "FAILED" in sts: print("FAILED")
elif "IN_PROGRESS" in sts: print("IN_PROGRESS")
elif sts: print("SUCCEEDED")
else: print("UNKNOWN")
' 2>/dev/null || echo UNKNOWN)"
  case "$IM_STATUS" in
    SUCCEEDED|FAILED) break ;;
    *) printf '.' ;;
  esac
done
echo
if [ "$IM_STATUS" = "SUCCEEDED" ]; then
  ok "interaction models built"
else
  fail "interaction model build status: $IM_STATUS. Inspect: ask smapi get-skill-status -s $SKILL_ID --resource interactionModel"
  exit 1
fi

say "Enabling Development testing"
if ask smapi set-skill-enablement -s "$SKILL_ID" -g development >/dev/null 2>&1; then
  ok "development stage enabled"
else
  warn "could not enable automatically (often already enabled). If needed: Developer Console -> Test -> Development."
fi

echo
ok "Done. Try it:"
echo "     ask dialog --locale en-US        (then: open claudius)"
echo "     ask dialog --locale de-DE        (then: öffne claudius)"
echo "     On your Echo: \"Alexa, open claudius\" / \"Alexa, öffne claudius\""
