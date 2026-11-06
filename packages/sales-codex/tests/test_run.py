#!/usr/bin/env python3
"""Package tests for the codex harness `run`: it is driven against recorded `codex exec --json`
streams (the tests/fixtures/*.jsonl files), and each turn's stdout is validated with hgkit.check,
the same reader the platform uses.

Run from anywhere:  python3 tests/test_run.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/opt/hg/lib")
from hgkit import check  # noqa: E402

PKG = Path(__file__).resolve().parents[1]
FAKE = PKG / "tests" / "fake_codex"
FIX = PKG / "tests" / "fixtures"


def mk(tmp=None):
    """A fresh sandbox layout for one turn; returns its root. Pass an existing root to reuse it."""
    tmp = Path(tmp or tempfile.mkdtemp(prefix="codex-test-"))
    tools = tmp / "tools"
    (tools / "bin").mkdir(parents=True, exist_ok=True)
    link = tools / "bin" / "codex"
    if not link.exists():
        os.symlink(FAKE, link)
    for d in ("workspace", "state", "home"):
        (tmp / d).mkdir(exist_ok=True)
    return tmp


def run_package(request, tmp, env_overrides=None, history=None):
    """Run one turn of the package against the fake codex at tmp, returning the subprocess result."""
    req_file = tmp / "request.json"
    req_file.write_text(json.dumps(request))
    hist_file = tmp / "history.json"
    hist_file.write_text(json.dumps(history or []))
    env = {
        "HG_REQUEST": str(req_file),
        "HG_TOOLS": str(tmp / "tools"),
        "HG_WORKSPACE": str(tmp / "workspace"),
        "HG_STATE": str(tmp / "state"),
        "HG_PACKAGE_DIR": str(PKG),
        "HG_MODEL": "deepseek-v4-pro",
        "HG_PROVIDER_URL": "http://127.0.0.1:9096",
        "HG_PROVIDER_API": "openai",
        "HG_PROVIDER_TOKEN": "test-token",
        "HG_HISTORY": str(hist_file),
        "HG_PACKAGE_VERSION": "0.167.0-1",
        "HOME": str(tmp / "home"),
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": "/opt/hg/lib" + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else ""),
        "FAKE_CODEX_ARGV": str(tmp / "argv"),
    }
    env.update(env_overrides or {})
    proc = subprocess.run([sys.executable, str(PKG / "run")], env=env, capture_output=True, text=True, timeout=90)
    return proc


def item_types(events):
    return [e.get("type") for e in events]


def output_items(outcome):
    return [i.get("type") for i in outcome.output]


def test_text_turn():
    tmp = mk()
    proc = run_package({"input": "Research Acme Corp"}, tmp,
                       {"FAKE_CODEX_OUTPUT": str(FIX / "text.jsonl"), "FAKE_CODEX_EXIT": "0"})
    events, outcome = check(proc.stdout)
    assert proc.returncode == 0, proc.stderr
    assert outcome.status == "completed", proc.stdout
    assert "response.output_text.done" in item_types(events)
    assert any(i.get("type") == "message" and "Mock reply 1" in (i.get("content") or [{}])[0].get("text", "")
               for i in outcome.output)
    assert "resume" not in (tmp / "argv").read_text()


def test_tool_turn():
    tmp = mk()
    proc = run_package({"input": "run a command"}, tmp,
                       {"FAKE_CODEX_OUTPUT": str(FIX / "tool.jsonl"), "FAKE_CODEX_EXIT": "0"})
    events, outcome = check(proc.stdout)
    assert outcome.status == "completed", proc.stdout
    assert "shell_call" in output_items(outcome)
    shell = next(i for i in outcome.output if i.get("type") == "shell_call")
    assert "hello-from-tool" in (shell.get("action") or {}).get("commands", [""])[0]
    assert "resume" not in (tmp / "argv").read_text()


def test_resume_from_saved_session():
    tmp = mk()
    (tmp / "state" / "session").write_text("01a1afab-159d-7612-9072-bbbc1cf5b1d6")
    proc = run_package({"input": "continue"}, tmp,
                       {"FAKE_CODEX_OUTPUT": str(FIX / "resumed.jsonl"), "FAKE_CODEX_EXIT": "0"})
    events, outcome = check(proc.stdout)
    assert outcome.status == "completed", proc.stdout
    argv = (tmp / "argv").read_text()
    assert "resume" in argv and "01a1afab-159d-7612-9072-bbbc1cf5b1d6" in argv, argv


def test_resume_refused_falls_back_to_history():
    tmp = mk()
    (tmp / "state" / "session").write_text("dead-session")
    history = [{
        "id": "r_1", "status": "completed",
        "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Who are they?"}]}],
        "output": [{"type": "message", "role": "assistant",
                    "content": [{"type": "output_text", "text": "Acme is a widget maker."}]}],
    }]
    proc = run_package({"input": "again"}, tmp,
                       {"FAKE_CODEX_OUTPUT": "/dev/null", "FAKE_CODEX_EXIT": "1",
                        "FAKE_CODEX_OUTPUT_2": str(FIX / "text.jsonl"), "FAKE_CODEX_EXIT_2": "0",
                        "FAKE_CODEX_STDIN_FILE": str(tmp / "stdin")},
                       history=history)
    events, outcome = check(proc.stdout)
    assert outcome.status == "completed", proc.stdout
    argv = (tmp / "argv").read_text().splitlines()
    assert len(argv) == 2, argv
    assert "resume" in argv[0] and "dead-session" in argv[0], argv
    assert "resume" not in argv[1], argv
    stdin = (tmp / "stdin").read_text()
    assert "Earlier in this conversation" in stdin, stdin
    assert "Acme is a widget maker." in stdin, stdin


def test_provider_error():
    tmp = mk()
    proc = run_package({"input": "anything"}, tmp,
                       {"FAKE_CODEX_OUTPUT": str(FIX / "err401.jsonl"), "FAKE_CODEX_EXIT": "1"})
    events, outcome = check(proc.stdout)
    assert outcome.status == "failed", proc.stdout
    assert outcome.error is not None


def test_timeout():
    tmp = mk()
    proc = run_package({"input": "anything"}, tmp,
                       {"FAKE_CODEX_OUTPUT": str(FIX / "text.jsonl"), "FAKE_CODEX_SLEEP": "5",
                        "HG_CODEX_TIMEOUT_S": "0.2"})
    events, outcome = check(proc.stdout)
    assert outcome.status == "failed", proc.stdout
    assert "did not finish" in (outcome.error or {}).get("message", ""), proc.stdout


def test_workspace_diff_reports_new_file():
    tmp = mk()
    proc = run_package({"input": "write a brief"}, tmp,
                       {"FAKE_CODEX_OUTPUT": str(FIX / "text.jsonl"), "FAKE_CODEX_EXIT": "0",
                        "FAKE_CODEX_WRITE_FILE": str(tmp / "workspace" / "brief.md"),
                        "FAKE_CODEX_WRITE_CONTENT": "Acme brief\n"})
    events, outcome = check(proc.stdout)
    assert outcome.status == "completed", proc.stdout
    assert "apply_patch_call" in output_items(outcome)
    patch = next(i for i in outcome.output if i.get("type") == "apply_patch_call")
    assert patch["operation"]["type"] == "create_file"
    assert patch["operation"]["path"] == "brief.md"


def test_instructions_reach_the_prompt():
    tmp = mk()
    proc = run_package({"instructions": "You are a sales agent.", "input": "Draft an email"}, tmp,
                       {"FAKE_CODEX_OUTPUT": str(FIX / "text.jsonl"), "FAKE_CODEX_EXIT": "0",
                        "FAKE_CODEX_STDIN_FILE": str(tmp / "stdin")})
    events, outcome = check(proc.stdout)
    assert outcome.status == "completed", proc.stdout
    stdin = (tmp / "stdin").read_text()
    assert "You are a sales agent." in stdin, stdin
    assert "Draft an email" in stdin, stdin


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print("PASS", fn.__name__)
        except Exception:
            failed += 1
            print("FAIL", fn.__name__)
            traceback.print_exc()
    sys.exit(1 if failed else 0)
