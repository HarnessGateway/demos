"""The social-claude-code package, tested the way the sandbox runs it: `run` with a fake `claude` on PATH that
replays a recorded stream, and the PreToolUse guard fed tool calls directly. Every output line is checked with
hgkit's reader — the one the platform itself uses."""
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import NamedTuple

from hgkit import check

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "run"
FAKE = ROOT / "tests" / "fake_claude"
FIXTURES = ROOT / "tests" / "fixtures"
GUARD = ROOT / "seeds" / "home" / ".claude" / "hooks" / "guard.py"
HGKIT = Path("/opt/hg/lib")          # hgkit lives here in the sandbox image
PLACEHOLDER = "hgs_placeholder_test"  # the secret placeholder a turn would see; must never reach the output


class Turn(NamedTuple):
    outcome: object
    argv: str
    stdin: str
    stdout: str


def turn(tmp_path: Path, body: dict, fixture: str, history: dict | None = None, env_extra: dict | None = None) -> Turn:
    """One turn of `run` against the fake claude; returns the outcome and what the fake claude saw."""
    request = tmp_path / "request.json"
    request.write_text(json.dumps(body))
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    (bindir / "claude").write_text(FAKE.read_text())
    (bindir / "claude").chmod(0o755)
    (tmp_path / "ws").mkdir(exist_ok=True)
    fake_log = tmp_path / f"fake-{uuid.uuid4().hex}.log"   # fresh per turn: the fake appends, so a shared log would
    env = {**os.environ,                                    # leave this turn reading the previous turn's ARGV line
           "HG_REQUEST": str(request), "HG_WORKSPACE": str(tmp_path / "ws"), "HG_STATE": str(tmp_path / "state"),
           "HOME": str(tmp_path / "home"), "HG_MODEL": "deepseek-v4-pro",
           "HG_PROVIDER_URL": "https://api.deepseek.com/anthropic", "HG_PROVIDER_TOKEN": PLACEHOLDER,
           "HG_PACKAGE_VERSION": "2.1.319-1",
           "PYTHONPATH": f"{HGKIT}{os.pathsep}{os.environ.get('PYTHONPATH', '')}",
           "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}",
           "FAKE_FIXTURE": str(FIXTURES / fixture), "FAKE_LOG": str(fake_log)}
    if history is not None:
        hist = tmp_path / "history.json"
        hist.write_text(json.dumps(history))
        env["HG_HISTORY"] = str(hist)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run([sys.executable, str(RUN)], cwd=tmp_path / "ws", env=env,
                          capture_output=True, text=True)
    log = fake_log.read_text() if fake_log.exists() else ""
    argv = next((l for l in log.splitlines() if l.startswith("ARGV:")), "")
    stdin = "\n".join(l for l in log.splitlines() if not l.startswith("ARGV:"))
    _events, outcome = check(proc.stdout)
    return Turn(outcome, argv, stdin, proc.stdout)


def test_a_completed_turn(tmp_path):
    t = turn(tmp_path, {"input": "do the fixture thing"}, "success.jsonl")
    assert t.outcome.status == "completed"
    kinds = [i["type"] for i in t.outcome.output]
    assert kinds == ["message", "shell_call", "shell_call_output", "message"]
    text = "".join(p.get("text", "") for i in t.outcome.output if i["type"] == "message"
                   for p in i["content"] if p.get("type") == "output_text")
    assert "Hello from the fixture." in text
    assert t.outcome.output[1]["action"]["commands"] == ["echo fixture-ok"]
    assert t.outcome.metadata["claude_session_id"] == "11111111-1111-4111-8111-111111111111"


def test_denied_bash_maps_the_refusal(tmp_path):
    t = turn(tmp_path, {"input": "post something"}, "denied_post.jsonl")
    assert t.outcome.status == "completed"
    result = t.outcome.output[1]
    assert result["type"] == "shell_call_output"
    assert "would send data (POST/PUT/PATCH/DELETE)" in result["output"][0]["stderr"]
    assert result["output"][0]["outcome"] == {"type": "exit", "exit_code": 1}


def test_deny_list_git_is_refused(tmp_path):
    t = turn(tmp_path, {"input": "push it"}, "denied_git.jsonl")
    assert t.outcome.status == "completed"
    result = t.outcome.output[1]
    assert "has been denied" in result["output"][0]["stderr"]


def test_provider_error_fails_the_turn(tmp_path):
    t = turn(tmp_path, {"input": "say hi"}, "provider_error.jsonl")
    assert t.outcome.status == "failed"
    assert t.outcome.error["code"] == "authentication_error"


def test_max_turns_stops_incomplete(tmp_path):
    t = turn(tmp_path, {"input": "long job"}, "max_turns.jsonl")
    assert t.outcome.status == "incomplete"
    assert t.outcome.incomplete["reason"] == "max_messages"


def test_session_is_saved_then_resumed(tmp_path):
    t1 = turn(tmp_path, {"input": "first"}, "success.jsonl")
    assert "--resume" not in t1.argv
    sid = (tmp_path / "state" / "session").read_text().strip()
    assert sid == "11111111-1111-4111-8111-111111111111"
    t2 = turn(tmp_path, {"input": "second"}, "success.jsonl")
    assert f"--resume {sid}" in t2.argv


def test_history_continues_when_no_session(tmp_path):
    prior = [{"id": "resp_prior", "status": "completed",
              "input": [{"type": "message", "role": "user",
                         "content": [{"type": "input_text", "text": "Remember the number 7."}]}],
              "output": [{"type": "message", "role": "assistant",
                          "content": [{"type": "output_text", "text": "ok"}]}]}]
    t = turn(tmp_path, {"input": "what number?"}, "success.jsonl", history=prior)
    assert t.outcome.status == "completed"
    assert "Earlier in this conversation" in t.stdin and "Remember the number 7." in t.stdin


def test_metadata_names_the_campaign(tmp_path):
    body = {"input": "draft it", "metadata": {"campaign": "launch", "platforms": ["x", "linkedin"]}}
    t = turn(tmp_path, body, "success.jsonl")
    assert "Campaign slug: launch" in t.stdin and "Platforms to post on: x, linkedin" in t.stdin


def test_no_secret_reaches_the_output(tmp_path):
    t = turn(tmp_path, {"input": "do the fixture thing"}, "success.jsonl")
    assert PLACEHOLDER not in t.stdout


def test_empty_input_fails(tmp_path):
    t = turn(tmp_path, {"input": ""}, "success.jsonl")
    assert t.outcome.status == "failed" and t.outcome.error["code"] == "invalid_prompt"


def _guard(tool: dict) -> str:
    """The PreToolUse guard, run as Claude Code runs it (JSON on stdin, the deny decision on stdout)."""
    env = {**os.environ, "HG_WORKSPACE": "/workspace"}
    proc = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(tool),
                          capture_output=True, text=True, env=env)
    return proc.stdout


def test_guard_allows_reads_and_workspace_writes():
    assert _guard({"tool_name": "Bash", "tool_input": {"command": "curl -sL https://example.com/article"}}) == ""
    assert _guard({"tool_name": "Write", "tool_input": {"file_path": "/workspace/campaigns/slug/x.md"}}) == ""
    assert _guard({"tool_name": "WebFetch", "tool_input": {"url": "https://example.com/article"}}) == ""


def test_guard_denies_posting_social_hosts_and_outside_writes():
    for cmd in ["curl -X POST -d x=1 https://example.com/submit",
                "wget --post-data x=1 https://example.com/submit",
                "http POST https://example.com/submit x=1"]:
        assert "would send data" in _guard({"tool_name": "Bash", "tool_input": {"command": cmd}})
    for url in ["https://api.twitter.com/2/tweets", "https://bsky.social/xrpc/x"]:
        assert "social platform's API host" in _guard({"tool_name": "WebFetch", "tool_input": {"url": url}})
    assert "social platform's API host" in _guard(
        {"tool_name": "Bash", "tool_input": {"command": "curl -s https://api.twitter.com/2/tweets"}})
    assert "under /api/" in _guard(
        {"tool_name": "Bash", "tool_input": {"command": "curl -s https://mastodon.social/api/v1/timelines/public"}})
    assert "outside the workspace" in _guard({"tool_name": "Write", "tool_input": {"file_path": "/etc/x.txt"}})
    assert "outside the workspace" in _guard({"tool_name": "Edit", "tool_input": {"file_path": "~/x.md"}})
