import json
import stat
import subprocess
from pathlib import Path

import pytest

import deploy_helpers as dh

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "scripts" / "deploy.sh"

LIVE_APIS = {"custom": {
    "endpoint": {"uri": "arn:aws:lambda:eu-west-1:000000000000:function:live"},
    "regions": {"EU": {"endpoint": {
        "uri": "arn:aws:lambda:eu-west-1:000000000000:function:live"}}},
}}


def _run(*args):
    return subprocess.run(["bash", str(DEPLOY), *args], capture_output=True,
                          text=True, timeout=30)


def _write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def source_manifest(tmp_path):
    return _write_json(tmp_path / "skill.json", {"manifest": {
        "apis": {"custom": {}},
        "publishingInformation": {"category": "EDUCATION_AND_REFERENCE"},
    }})


# --- deploy.sh argument handling (runs before any prerequisite check) ------

def test_help_lists_every_option_and_exits_cleanly():
    result = _run("--help")
    assert result.returncode == 0
    for option in ("--check", "--skip-tests", "--set-key", "CLAUDIUS_HOSTED_DIR"):
        assert option in result.stdout


def test_unknown_option_is_rejected_not_taken_as_hosted_dir():
    result = _run("--chekc")
    assert result.returncode == 2
    assert "--chekc" in result.stderr


# --- manifest merge --------------------------------------------------------

def test_merge_keeps_the_live_lambda_endpoint(tmp_path, source_manifest):
    live = _write_json(tmp_path / "live.json", {"manifest": {
        "apis": LIVE_APIS, "publishingInformation": {"category": "OLD"}}})
    out = tmp_path / "out.json"

    dh.merge_manifest(source_manifest, live, out)

    merged = json.loads(out.read_text(encoding="utf-8"))["manifest"]
    assert merged["apis"] == LIVE_APIS
    assert merged["publishingInformation"] == {"category": "EDUCATION_AND_REFERENCE"}


@pytest.mark.parametrize("live_content", [
    None,                                            # fetch failed: no file
    "",                                              # fetch failed: empty file
    json.dumps({"manifest": {"apis": {"custom": {}}}}),  # endpoint already gone
])
def test_merge_refuses_to_upload_a_manifest_without_endpoint(
        tmp_path, source_manifest, live_content):
    live = tmp_path / "live.json"
    if live_content is not None:
        live.write_text(live_content, encoding="utf-8")
    out = tmp_path / "out.json"

    with pytest.raises(dh.DeployError, match="endpoint"):
        dh.merge_manifest(source_manifest, live, out)
    assert not out.exists()


# --- config.py generation --------------------------------------------------

def _load_key(config_path):
    namespace = {}
    exec(config_path.read_text(encoding="utf-8"), namespace)
    return namespace["ANTHROPIC_API_KEY"]


@pytest.mark.parametrize("key", [
    "sk-ant-api03-abc_DEF-123",
    'sk-ant-we&ird|k\\ey"with\'quotes',   # would corrupt a sed replacement
])
def test_config_is_written_with_the_exact_key(tmp_path, key):
    out = tmp_path / "config.py"
    dh.write_config(ROOT / "lambda" / "config.example.py", out, key)
    assert _load_key(out) == key


def test_config_is_readable_by_owner_only(tmp_path):
    out = tmp_path / "config.py"
    out.write_text("old", encoding="utf-8")   # rotation: replaces an existing file
    out.chmod(0o644)
    dh.write_config(ROOT / "lambda" / "config.example.py", out, "sk-ant-new")
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    assert _load_key(out) == "sk-ant-new"


@pytest.mark.parametrize("key", ["", "sk-ant-a b", "sk-ant-a\nb"])
def test_config_rejects_a_mangled_key(tmp_path, key):
    out = tmp_path / "config.py"
    with pytest.raises(dh.DeployError, match="key"):
        dh.write_config(ROOT / "lambda" / "config.example.py", out, key)
    assert not out.exists()


def test_config_fails_when_the_template_has_no_placeholder(tmp_path):
    template = tmp_path / "config.example.py"
    template.write_text('ANTHROPIC_API_KEY = "something-else"\n', encoding="utf-8")
    with pytest.raises(dh.DeployError, match="placeholder"):
        dh.write_config(template, tmp_path / "config.py", "sk-ant-x")


# --- skill id lookup -------------------------------------------------------

def test_skill_id_is_read_from_ask_states(tmp_path):
    states = _write_json(tmp_path / "ask-states.json", {"askcliStatesVersion": "2020-03-31",
        "profiles": {"default": {"skillId": "amzn1.ask.skill.test"}}})
    assert dh.read_skill_id(states) == "amzn1.ask.skill.test"


def test_skill_id_is_empty_when_states_file_is_missing(tmp_path):
    assert dh.read_skill_id(tmp_path / "nope.json") == ""


# --- lambda sync -----------------------------------------------------------

def test_sync_mirrors_sources_but_never_touches_the_key(tmp_path):
    src, dst = tmp_path / "lambda", tmp_path / "hosted" / "lambda"
    src.mkdir()
    dst.mkdir(parents=True)
    (src / "lambda_function.py").write_text("new", encoding="utf-8")
    (src / "new_module.py").write_text("added", encoding="utf-8")
    (src / "requirements.txt").write_text("anthropic", encoding="utf-8")
    (src / "config.example.py").write_text("template", encoding="utf-8")
    (src / "config.py").write_text("LOCAL-KEY", encoding="utf-8")
    (dst / "lambda_function.py").write_text("old", encoding="utf-8")
    (dst / "removed_module.py").write_text("stale", encoding="utf-8")
    (dst / "config.py").write_text("DEPLOYED-KEY", encoding="utf-8")

    removed = dh.sync_lambda(src, dst)

    assert {p.name: p.read_text(encoding="utf-8") for p in dst.iterdir()} == {
        "lambda_function.py": "new",
        "new_module.py": "added",
        "requirements.txt": "anthropic",
        "config.py": "DEPLOYED-KEY",
    }
    assert removed == ["removed_module.py"]
