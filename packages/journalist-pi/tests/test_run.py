#!/usr/bin/env python3
"""Package test: run `run` against recorded pi output (replayed by a stub pi in a scratch
$HG_TOOLS) and check every line with hgkit.check. No network, no real pi."""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from hgkit import check
from hgkit.validate import OutputError

PKG = Path(__file__).resolve().parent.parent
RUN = PKG / "run"
FIX = PKG / "tests" / "fixtures"
CASES = json.loads((PKG / "tests" / "cases.json").read_text())

STUB = """#!/usr/bin/env python3
import os, sys, time
mode = os.environ.get("HG_TEST_MODE", "")
base = os.environ.get("HG_TEST_FIXDIR", "")
if mode == "sleep":
    print('{"type":"session","version":3,"id":"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",'
          '"timestamp":"2026-11-06T00:00:00.000Z","cwd":"/workspace"}')
    sys.stdout.flush()
    time.sleep(600)
    sys.exit(0)
argv_path = os.environ.get("HG_TEST_ARGV")
if argv_path:
    with open(argv_path, "w") as f:
        f.write("\\n".join(sys.argv))
for name, stream in (("stdout", sys.stdout), ("stderr", sys.stderr)):
    p = os.path.join(base, mode + "." + name)
    if os.path.exists(p):
        stream.write(open(p, encoding="utf-8").read())
        stream.flush()
code = 0
p = os.path.join(base, mode + ".exit")
if os.path.exists(p):
    code = int(open(p).read().strip() or 0)
sys.exit(code)
"""


def assignment(name):
    return {"input": [{"type": "message", "role": "user",
                       "content": [{"type": "input_text", "text": "Test assignment: " + name}]}]}


def first_line_id(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get("type") == "session":
                return d.get("id", "")
    return ""


def setup():
    td = Path(tempfile.mkdtemp(prefix="pkgtest-"))
    (td / "tools" / "node_modules" / ".bin").mkdir(parents=True)
    stub = td / "tools" / "node_modules" / ".bin" / "pi"
    stub.write_text(STUB)
    stub.chmod(0o755)
    (td / "workspace").mkdir()
    home = td / "home"
    (home / ".pi" / "agent").mkdir(parents=True)
    state = td / "state"
    state.mkdir()
    env = os.environ.copy()
    env.update({
        "HG_TOOLS": str(td / "tools"),
        "HG_WORKSPACE": str(td / "workspace"),
        "HG_REQUEST": str(td / "request.json"),
        "HG_STATE": str(state),
        "HOME": str(home),
        "HG_MODEL": "deepseek-v4-pro",
        "HG_PROVIDER_URL": "http://hg-door:8080",
        "HG_PROVIDER_API": "anthropic",
        "HG_PROVIDER_TOKEN": "test-token",
        "HG_PACKAGE_VERSION": "0.73.1-1",
        "HG_TEST_FIXDIR": str(FIX),
        "PI_SKIP_VERSION_CHECK": "1",
        "PI_OFFLINE": "1",
    })
    return td, env


def seed_session(home, sid, fixture):
    sdir = Path(home) / ".pi" / "agent" / "sessions" / "--workspace--"
    sdir.mkdir(parents=True, exist_ok=True)
    target = sdir / ("2026-11-06T00-00-00-000Z_" + sid + ".jsonl")
    target.write_bytes(Path(fixture).read_bytes())
    return target


def run_turn(env, mode, body, extra_env=None):
    env = dict(env)
    env["HG_TEST_MODE"] = mode
    if extra_env:
        env.update(extra_env)
    Path(env["HG_WORKSPACE"]).mkdir(exist_ok=True)
    Path(env["HG_REQUEST"]).write_text(json.dumps(body))
    return subprocess.run([sys.executable, str(RUN)], env=env, capture_output=True, text=True, timeout=120)


def check_output(proc):
    try:
        events, outcome = check(proc.stdout)
    except OutputError as e:
        raise AssertionError("invalid output: %s\n--- run stdout ---\n%s\n--- run stderr ---\n%s"
                             % (e, proc.stdout, proc.stderr)) from None
    return events, outcome


def main():
    failures = []
    for case in CASES:
        td, env = setup()
        name = case["name"]
        argv_log = td / "argv.txt"
        extra = {"HG_TEST_ARGV": str(argv_log)} if case.get("resume_from") else None
        body = assignment(name)
        if PKG.name == "journalist-pi":
            body["metadata"] = {"desk": "biofuels", "task": "briefing"}

        if case.get("resume_from"):
            parent = case["resume_from"]
            parent_sid = first_line_id(FIX / (parent + ".stdout"))
            assert parent_sid, parent + " fixture has no session header"
            seed_session(env["HOME"], parent_sid, FIX / (parent + ".stdout"))
            (Path(env["HG_STATE"]) / "session").write_text(parent_sid)

        proc = run_turn(env, case["mode"], body, extra)
        try:
            assert proc.returncode == 0, "run exited %s: %s" % (proc.returncode, proc.stderr)
            events, outcome = check_output(proc)
            assert outcome.status == case["status"], "%s: %s" % (outcome.status, outcome)

            if case.get("error_code"):
                assert outcome.error and outcome.error.get("code") == case["error_code"], outcome.error

            if case.get("shell"):
                assert any(e.get("type") == "response.output_item.done"
                           and (e.get("item") or {}).get("type") == "shell_call" for e in events), \
                    "no shell_call item"

            if case.get("patch_failed"):
                assert any(e.get("type") == "response.output_item.done"
                           and (e.get("item") or {}).get("type") == "apply_patch_call_output"
                           and (e.get("item") or {}).get("status") == "failed" for e in events), \
                    "no failed apply_patch_call_output"

            if case.get("resume_from"):
                args = argv_log.read_text().split("\n")
                assert "--session" in args, args
                sidx = args.index("--session")
                resumed_sid = first_line_id(FIX / (case["mode"] + ".stdout"))
                assert args[sidx + 1].endswith(resumed_sid + ".jsonl"), args

            sid = first_line_id(FIX / (case["mode"] + ".stdout"))
            if sid:
                saved = (Path(env["HG_STATE"]) / "session").read_text()
                assert saved == sid, "state session %r != %r" % (saved, sid)

            print("ok: %-18s -> %-9s (%d events, %d output items)"
                  % (name, outcome.status, len(events), len(outcome.output)))
        except AssertionError as e:
            failures.append((name, str(e)))
            print("FAIL: %s: %s" % (name, e))

    # the interrupted path: SIGTERM to run mid-turn; run must still end with a terminal event and
    # the session id must already be saved.
    td, env = setup()
    env["HG_TEST_MODE"] = "sleep"
    body = assignment("sigterm")
    if PKG.name == "journalist-pi":
        body["metadata"] = {"desk": "biofuels", "task": "briefing"}
    Path(env["HG_REQUEST"]).write_text(json.dumps(body))
    try:
        proc = subprocess.Popen([sys.executable, str(RUN)], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(2.0)
        proc.send_signal(signal.SIGTERM)
        out_text, _err = proc.communicate(timeout=30)
        _events, outcome = check(out_text)
        assert outcome.status == "failed" and outcome.error and outcome.error.get("code") == "interrupted", \
            (outcome, out_text)
        saved = (Path(env["HG_STATE"]) / "session").read_text()
        assert saved == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", saved
        print("ok: %-18s -> %-9s (SIGTERM interrupted, session id saved)" % ("sigterm", outcome.status))
    except (AssertionError, OutputError) as e:
        failures.append(("sigterm", str(e)))
        print("FAIL: sigterm: %s" % e)

    print("\n%d cases, %d failures" % (len(CASES) + 1, len(failures)))
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
