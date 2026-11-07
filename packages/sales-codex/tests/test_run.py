"""`run` executed as the sandbox executes it, against a fake `codex` that replays recorded
JSONL fixtures; every line `run` prints is checked with hgkit's reader, the one the platform uses."""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from hgkit import check

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "run"
BIN = Path(__file__).resolve().parent / "bin"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def make_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    env = {**os.environ}
    env.update({
        "PATH": f"{BIN}:{os.environ.get('PATH', '')}",
        "PYTHONPATH": "/opt/hg/lib",
        "HG_REQUEST": str(tmp_path / "request.json"),
        "HG_WORKSPACE": str(tmp_path),
        "HG_STATE": str(tmp_path / "state"),
        "HG_HISTORY": str(tmp_path / "history.json"),
        "HG_PACKAGE_DIR": str(ROOT),
        "HG_PACKAGE_VERSION": "0.167.0-1",
        "HG_MODEL": "deepseek-v4-pro",
        "HG_PROVIDER_API": "openai",
        "HG_PROVIDER_URL": "https://relay.example",
        "HG_PROVIDER_TOKEN": "hgs_test_token_placeholder",
        "HG_TOOLS": str(tmp_path / "tools"),
        "HOME": str(tmp_path / "home"),
        "STORE_PROFILE": "A test store that sells flooring.",
        "SIGNATURE": "— Test team",
    })
    env.update(extra)
    return env


def turn(tmp_path: Path, body: dict, fixture: str | None = None, **extra: str):
    (tmp_path / "request.json").write_text(json.dumps(body))
    env = make_env(tmp_path, **extra)
    if fixture:
        env["FAKE_CODEX_FIXTURE"] = str(FIXTURES / fixture)
    proc = subprocess.run([sys.executable, str(RUN)], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=120)
    return proc, *check(proc.stdout)


def items(outcome) -> list[dict]:
    return outcome.output


def test_text_turn_maps_and_saves_session(tmp_path):
    proc, events, outcome = turn(tmp_path, {"input": "Who is overdue?"}, fixture="text.jsonl")
    assert outcome.status == "completed"
    assert [i["type"] for i in items(outcome)] == ["message"]
    assert "Alice Ortega" in items(outcome)[0]["content"][0]["text"]
    assert outcome.usage["input_tokens"] == 120
    assert outcome.metadata["codex_version"] == "0.167.0"
    assert (tmp_path / "state" / "session").read_text() == "sess-text-0001"


def test_tool_turn_maps_shell_call(tmp_path):
    _, _, outcome = turn(tmp_path, {"input": "How many customers?"}, fixture="tool.jsonl")
    kinds = [i["type"] for i in items(outcome)]
    assert kinds == ["shell_call", "shell_call_output", "message"]
    assert items(outcome)[1]["output"][0]["stdout"] == "42 customers\n"
    assert items(outcome)[1]["output"][0]["outcome"] == {"type": "exit", "exit_code": 0}


def test_reasoning_maps_to_reasoning_item(tmp_path):
    _, _, outcome = turn(tmp_path, {"input": "Think it through."}, fixture="reasoning.jsonl")
    assert [i["type"] for i in items(outcome)] == ["reasoning", "message"]
    assert outcome.usage["output_tokens_details"]["reasoning_tokens"] == 25


def test_forbidden_command_is_a_failed_shell_call(tmp_path):
    _, _, outcome = turn(tmp_path, {"input": "Push the changes."}, fixture="forbidden.jsonl")
    assert outcome.status == "completed"
    kinds = [i["type"] for i in items(outcome)]
    assert kinds == ["shell_call", "shell_call_output", "message"]
    assert items(outcome)[1]["output"][0]["outcome"] == {"type": "exit", "exit_code": 1}
    assert "rejected" in items(outcome)[1]["output"][0]["stdout"]


def test_provider_error_fails_the_turn(tmp_path):
    _, _, outcome = turn(tmp_path, {"input": "Who is overdue?"}, fixture="provider-error.jsonl")
    assert outcome.status == "failed"
    assert outcome.error["code"] == "rate_limit_exceeded"


def test_resume_uses_saved_session(tmp_path):
    turn(tmp_path, {"input": "Who is overdue?"}, fixture="text.jsonl")
    rec = tmp_path / "fake.log"
    _, _, outcome = turn(tmp_path, {"input": "And who else?"}, fixture="resume.jsonl",
                         FAKE_CODEX_RECORD=str(rec))
    assert outcome.status == "completed"
    calls = [json.loads(l) for l in rec.read_text().splitlines()]
    assert "resume" in calls[-1]["argv"]
    assert "sess-text-0001" in calls[-1]["argv"]
    assert "conversation-so-far" not in calls[-1]["stdin"]  # native resume needs no history


def test_history_is_the_fallback_without_a_session(tmp_path):
    (tmp_path / "history.json").write_text(json.dumps([{
        "id": "r1", "status": "completed",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "Who is overdue?"}]}],
        "output": [{"type": "message", "role": "assistant",
                    "content": [{"type": "output_text", "text": "Call Alice Ortega."}]}],
    }]))
    rec = tmp_path / "fake.log"
    _, _, outcome = turn(tmp_path, {"input": "And who else?"}, fixture="text.jsonl",
                         FAKE_CODEX_RECORD=str(rec))
    assert outcome.status == "completed"
    calls = [json.loads(l) for l in rec.read_text().splitlines()]
    assert "resume" not in calls[-1]["argv"]
    assert "conversation-so-far" in calls[-1]["stdin"]
    assert "Call Alice Ortega." in calls[-1]["stdin"]


def test_resume_falls_back_to_history_when_thread_lost(tmp_path):
    turn(tmp_path, {"input": "Who is overdue?"}, fixture="text.jsonl")
    (tmp_path / "history.json").write_text(json.dumps([{
        "id": "r1", "status": "completed",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "Who is overdue?"}]}],
        "output": [{"type": "message", "role": "assistant",
                    "content": [{"type": "output_text", "text": "Call Alice Ortega."}]}],
    }]))
    rec = tmp_path / "fake.log"
    _, _, outcome = turn(tmp_path, {"input": "And now?"}, fixture="text.jsonl",
                         FAKE_CODEX_RECORD=str(rec), FAKE_CODEX_RESUME_FAIL="1")
    assert outcome.status == "completed"
    calls = [json.loads(l) for l in rec.read_text().splitlines()]
    assert len(calls) == 2
    assert "resume" in calls[0]["argv"]
    assert "resume" not in calls[1]["argv"]
    assert "conversation-so-far" in calls[1]["stdin"]


def test_sigterm_is_a_cancelled_turn_with_the_session_saved(tmp_path):
    (tmp_path / "request.json").write_text(json.dumps({"input": "Slow question."}))
    env = make_env(tmp_path, FAKE_CODEX_HANG="1")
    proc = subprocess.Popen([sys.executable, str(RUN)], cwd=tmp_path, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            start_new_session=True)
    time.sleep(2)
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    out_text, _ = proc.communicate(timeout=60)
    _, outcome = check(out_text)
    assert outcome.status == "failed"
    assert outcome.error["code"] == "cancelled"
    assert (tmp_path / "state" / "session").read_text() == "sess-hang-0001"


def test_empty_input_fails_invalid_prompt(tmp_path):
    _, _, outcome = turn(tmp_path, {"input": ""})
    assert outcome.status == "failed"
    assert outcome.error["code"] == "invalid_prompt"


def test_input_file_is_placed_and_named(tmp_path):
    body = {"input": [{"role": "user", "content": [
        {"type": "input_text", "text": "Who is overdue?"},
        {"type": "input_file", "filename": "customers.json",
         "file_data": "data:application/json;base64,e30="},  # "{}"
    ]}]}
    rec = tmp_path / "fake.log"
    _, _, outcome = turn(tmp_path, body, fixture="text.jsonl", FAKE_CODEX_RECORD=str(rec))
    assert outcome.status == "completed"
    call = [json.loads(l) for l in rec.read_text().splitlines()][-1]
    assert "customers.json" in call["stdin"]
    assert (tmp_path / "customers.json").read_text() == "{}"


if __name__ == "__main__":
    # Run without pytest too: each test_* takes a tmp dir as its only argument.
    import tempfile
    import traceback as _tb
    names = [n for n in sorted(globals()) if n.startswith("test_")]
    passed = failed = 0
    for name in names:
        fn = globals()[name]
        with tempfile.TemporaryDirectory() as d:
            try:
                fn(Path(d))
            except Exception:
                print(f"FAIL {name}")
                _tb.print_exc()
                failed += 1
            else:
                print(f"PASS {name}")
                passed += 1
    print(f"{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
