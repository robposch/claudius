# Claudius

**Read `AGENTS.md` first.** It holds the rules for agents in this repo and
the deploy procedure, and points to the human documentation (`README.md`,
`docs/`) for the facts. This file only adds what is specific to Claude Code.

## Claude Code notes

- The interactive ASK wizards (`ask configure`, `ask new`, `ask init`; see
  AGENTS.md rule 3) cannot run through the Bash tool, and the `!` prefix does
  not help: it is a non-interactive shell too. Ask the user to run them in a
  separate terminal window.
- The same goes for the first deploy when no `ANTHROPIC_API_KEY` is exported:
  the hidden key prompt needs the user's own terminal.
- Deploys authenticate through the ASK CLI login only. Do not reach for the
  `aws` CLI or AWS credentials; none are involved.
