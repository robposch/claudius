#!/usr/bin/env python3
"""The file-handling steps of scripts/deploy.sh, kept in Python so they can be
tested (tests/test_deploy.py).

Standard library only, and no syntax newer than Python 3.8: this runs under
whatever `python3` is on the PATH of the machine that deploys.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

PLACEHOLDER = '"sk-ant-REPLACE-ME"'
KEY_ENV = "CLAUDIUS_API_KEY"

# Never copied into the hosted repo: the local key file (if someone made one)
# and the template it is generated from.
_NOT_SYNCED = {"config.py", "config.example.py"}


class DeployError(Exception):
    """A deploy step cannot continue; the message is shown to the user."""


def read_skill_id(states_path):
    """Skill id recorded by the ASK CLI in <hosted>/.ask/ask-states.json, or ""."""
    try:
        data = json.loads(Path(states_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    for profile in data.get("profiles", {}).values():
        if profile.get("skillId"):
            return profile["skillId"]
    return ""


def sync_lambda(src_dir, dst_dir):
    """Mirror the Lambda sources into the hosted repo.

    Copies every module plus requirements.txt, and deletes modules that no
    longer exist in the source. The hosted config.py (the API key) is never
    written or removed. Returns the names of the deleted modules.
    """
    src_dir, dst_dir = Path(src_dir), Path(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    sources = sorted(p for p in src_dir.glob("*.py") if p.name not in _NOT_SYNCED)
    for path in sources + [src_dir / "requirements.txt"]:
        shutil.copyfile(str(path), str(dst_dir / path.name))
    keep = {p.name for p in sources} | {"config.py"}
    stale = sorted(p for p in dst_dir.glob("*.py") if p.name not in keep)
    for path in stale:
        path.unlink()
    return [p.name for p in stale]


def merge_manifest(source_path, live_path, out_path):
    """Write the source manifest with the live manifest's `apis` section.

    Amazon injects the Lambda endpoint into `apis` when it provisions a hosted
    skill. Uploading a manifest without it disconnects the skill from its
    backend, so without a live endpoint to carry over this refuses to proceed.
    """
    source = json.loads(Path(source_path).read_text(encoding="utf-8"))
    try:
        live = json.loads(Path(live_path).read_text(encoding="utf-8"))
        apis = live.get("manifest", {}).get("apis") or {}
    except (OSError, ValueError):
        apis = {}
    if not (apis.get("custom") or {}).get("endpoint"):
        raise DeployError(
            "The live skill manifest has no Lambda endpoint to carry over (the "
            "fetch failed, or the endpoint is already gone). Not uploading the "
            "manifest, because that would disconnect the skill from its Lambda. "
            'See "During deploy" in docs/troubleshooting.md.')
    source["manifest"]["apis"] = apis
    Path(out_path).write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")


def write_config(template_path, out_path, key):
    """Generate config.py from the template, readable by its owner only."""
    if not key or any(ch.isspace() or ord(ch) < 32 for ch in key):
        raise DeployError(
            "The API key is empty or contains whitespace; check what was pasted.")
    template = Path(template_path).read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise DeployError(
            "%s does not contain the placeholder %s." % (template_path, PLACEHOLDER))
    # json.dumps yields a valid Python string literal whatever the key contains.
    content = template.replace(PLACEHOLDER, json.dumps(key))
    out_path = Path(out_path)
    fd, tmp_name = tempfile.mkstemp(dir=str(out_path.parent), prefix=".config-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:   # mkstemp: mode 0600
            handle.write(content)
        os.replace(tmp_name, str(out_path))
    except BaseException:
        os.unlink(tmp_name)
        raise


def main(argv):
    command, args = argv[0], argv[1:]
    try:
        if command == "skill-id":
            print(read_skill_id(args[0]))
        elif command == "sync-lambda":
            for name in sync_lambda(args[0], args[1]):
                print(name)
        elif command == "merge-manifest":
            merge_manifest(args[0], args[1], args[2])
        elif command == "write-config":
            # The key comes in through the environment, not argv, so it does
            # not show up in the process list.
            write_config(args[0], args[1], os.environ.get(KEY_ENV, ""))
        else:
            raise DeployError("unknown command: %s" % command)
    except DeployError as error:
        sys.stderr.write("%s\n" % error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
