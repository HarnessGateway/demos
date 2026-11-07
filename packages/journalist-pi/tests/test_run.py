"""`run` replaying recorded pi streams: every line it prints is checked with hgkit's reader, the one the platform
uses. No provider is reached — `JOURNALIST_PI_REPLAY` stands in for pi's stdout."""
import json
import os
import subprocess
import sys
from pathlib import Path

from hgkit import check

RUN = Path(__file__).resolve().parents[1] / "run"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
TEXT_ID = "01a1b4c0-1e89-76a6-9e10-cf43ef031107"


def turn(tmp_path: Path, body: dict, *, replay: str, fallback: str | None = None,
         state: str | None = None, token: str = "test-token-0000") -> tuple[list[dict], object]:
    request = tmp_path / "request.json"
    request.write_text(json.dumps(body))
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    state_dir = tmp_path / "state"
    state_dir.mkdir(exist_ok=True)
    if state:
        (state_dir / "session").write_text(state)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {
        **os.environ,
        "HG_REQUEST": str(request),
        "HG_WORKSPACE": str(ws),
        "HG_STATE": str(state_dir),
        "HG_TOOLS": "/opt/hg/tools",        # unused in replay mode
        "HG_MODEL": "deepseek-v4-pro",
        "HG_PROVIDER_API": "anthropic",
        "HG_PROVIDER_URL": "https://api.deepseek.com/anthropic",
        "HG_PROVIDER_TOKEN": token,
        "HOME": str(home),
        "JOURNALIST_PI_REPLAY": str(FIXTURES / replay),
    }
    if fallback:
        env["JOURNALIST_PI_REPLAY_FALLBACK"] = str(FIXTURES / fallback)
    proc = subprocess.run([sys.executable, str(RUN)], cwd=ws, env=env, capture_output=True, text=True, check=True)
    return check(proc.stdout)


def text_of(events: list[dict]) -> str:
    return "".join(e.get("delta", "") for e in events if e.get("type") == "response.output_text.delta")


def test_text_turn_completes_and_saves_the_session_id(tmp_path):
    events, outcome = turn(tmp_path, {"input": "Reply with exactly: hello desk."}, replay="text.jsonl")
    assert outcome.status == "completed"
    assert outcome.metadata["cli_session"] == TEXT_ID
    assert outcome.usage["output_tokens"] == 16
    assert outcome.usage["input_tokens"] == 2358
    assert text_of(events) == "hello desk."
    # continuity path 1: the session id is saved the moment it appears
    assert (tmp_path / "state" / "session").read_text() == TEXT_ID


def test_tool_calls_are_reported_as_calls(tmp_path):
    events, outcome = turn(tmp_path, {"input": "Echo and write a draft."}, replay="tool.jsonl")
    assert outcome.status == "completed"
    kinds = [item["type"] for item in outcome.output]
    assert "shell_call" in kinds and "apply_patch_call" in kinds
    shell = next(item for item in outcome.output if item["type"] == "shell_call")
    assert shell["action"]["commands"] == ["echo desk-ok"]
    patch = next(item for item in outcome.output if item["type"] == "apply_patch_call")
    assert patch["operation"]["path"] == "/workspace/desk/2026-11-07/test/draft.md"
    assert text_of(events) == "Done."


def test_killed_turn_ends_incomplete(tmp_path):
    _, outcome = turn(tmp_path, {"input": "Long assignment."}, replay="killed.jsonl")
    assert outcome.status == "incomplete"
    assert outcome.incomplete["reason"] == "max_output_tokens"


def test_provider_error_maps_to_a_code(tmp_path):
    _, outcome = turn(tmp_path, {"input": "Do the assignment."}, replay="error.jsonl")
    assert outcome.status == "failed"
    assert outcome.error["code"] == "authentication_error"


def test_length_stop_ends_incomplete(tmp_path):
    _, outcome = turn(tmp_path, {"input": "Long assignment."}, replay="length.jsonl")
    assert outcome.status == "incomplete"
    assert outcome.incomplete["reason"] == "max_output_tokens"


def test_refused_session_falls_back_to_a_fresh_run(tmp_path):
    # continuity path 2: a stale saved id makes pi refuse; run starts fresh from the history.
    events, outcome = turn(tmp_path, {"input": "Continue."}, replay="refused.jsonl",
                           fallback="text.jsonl", state="01a1b4c9-stale-stale-stale-stale999999")
    assert outcome.status == "completed"
    assert text_of(events) == "hello desk."     # only the fallback stream says this


def test_provider_token_is_scrubbed(tmp_path):
    events, _ = turn(tmp_path, {"input": "Say the token."}, replay="scrub.jsonl", token="SECRET")
    text = text_of(events)
    assert "SECRET" not in text and "***" in text
