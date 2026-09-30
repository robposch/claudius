# Template for the one secret the skill needs. Do not copy or edit this by
# hand: scripts/deploy.sh generates hosted/lambda/config.py from it (the
# hosted skill's private repo is the only place the real key lives), and
# `scripts/deploy.sh --set-key` replaces the key later.

# Create a dedicated API key for this skill at https://platform.claude.com/
ANTHROPIC_API_KEY = "sk-ant-REPLACE-ME"

# All other knobs (models, answer length, timeout, persona) live in lambda/settings.py
