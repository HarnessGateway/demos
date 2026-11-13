"""common/hg.py against a real platform: what every app does with it, using the `shell` harness so no model is needed.

    HG_TEST_URL=http://localhost:8000 HG_TEST_KEY=hg_...(an admin key) pytest tests/test_client.py
"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "common"))
from hg import FINAL, HG  # noqa: E402 - found through the path set above

URL, KEY = os.environ.get("HG_TEST_URL"), os.environ.get("HG_TEST_KEY")
pytestmark = pytest.mark.skipif(not (URL and KEY), reason="set HG_TEST_URL and HG_TEST_KEY to run against a platform")


def admin(method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(f"{URL}/v1{path}", method=method, data=json.dumps(body).encode(), headers={
        "authorization": f"Bearer {KEY}", "content-type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


@pytest.fixture(scope="module")
def hg() -> HG:
    """A client holding what an app holds: a key that can only run turns."""
    assert URL
    admin("POST", "/harnesses", {"catalog": "shell"})
    return HG(URL, admin("POST", "/keys", {"name": "demo-client-test", "role": "runner"})["key"], "shell")


def finished(hg: HG, turn: dict[str, Any]) -> dict[str, Any]:
    deadline = time.time() + 300
    while time.time() < deadline:
        response = hg.response(turn["id"])
        if response["status"] in FINAL:
            return response
        time.sleep(1)
    raise AssertionError("the turn did not finish")


def test_a_background_turn_with_a_file_and_the_work_it_leaves(hg: HG) -> None:
    turn = hg.start("cat inputs/customers.json; mkdir -p out/charts; echo '# Draft' > out/draft.md; echo png > out/charts/a.png",
                    user="tester", metadata={"app": "test"},
                    files={"customers.json": ("application/json", b'{"customers": 75}')})
    assert turn["status"] in ("queued", "in_progress")
    response = finished(hg, turn)
    assert response["status"] == "completed", response
    assert hg.text(response) == '{"customers": 75}'
    assert response["metadata"]["app"] == "test"

    session = hg.session(response)
    assert session.startswith("sess_")
    files = hg.folder(session, "out")
    assert sorted(file["rel"] for file in files) == ["charts/a.png", "draft.md"]
    assert hg.read_text(session, files, "draft.md") == "# Draft\n"
    assert hg.read_text(session, files, "missing.md") == ""


def test_a_follow_up_continues_the_session_and_a_fresh_file_replaces_the_old(hg: HG) -> None:
    first = finished(hg, hg.start("cat inputs/customers.json; echo kept > note.txt", user="tester",
                                  files={"customers.json": ("application/json", b"monday")}))
    second = finished(hg, hg.start("cat inputs/customers.json note.txt", user="tester", previous=first["id"],
                                   files={"customers.json": ("application/json", b"tuesday")}))
    assert hg.session(second) == hg.session(first)
    assert hg.text(second) == "tuesdaykept"


def test_progress_is_watched_while_a_turn_runs_and_a_turn_can_be_cancelled(hg: HG) -> None:
    seen: list[list[dict[str, Any]]] = []
    turn = hg.start("echo started; sleep 2; echo done", user="tester")
    hg.watch(turn["id"], seen.append)
    assert finished(hg, turn)["status"] == "completed"
    time.sleep(1)
    assert seen and seen[-1][-1]["type"] == "message"

    slow = hg.start("sleep 120", user="tester")
    time.sleep(2)
    hg.cancel(slow["id"])
    assert finished(hg, slow)["status"] == "cancelled"
