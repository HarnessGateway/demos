#!/usr/bin/env python3
"""Point the demos at a HarnessGateway: with an admin key, create one run-only key per app (named after the app, as the
platform means it), write each app's .env, and install the demo packages from packages/ (optional).

    scripts/setup.py --api http://localhost:8000 --admin-key-file ~/admin.key [--model deepseek-v4-pro] [--install]

A run-only key is what an application holds: it sends requests and reads the sessions it made, nothing more.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import tarfile
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPS = {"crm": "sales-codex", "market-desk": "journalist-pi"}
# the provider shape each harness speaks decides which of the organization's providers serves it
PROVIDER_FOR = {"sales-codex": "openai", "journalist-pi": "anthropic"}


def call(api: str, key: str, method: str, path: str, body: bytes | None = None, content_type: str = "application/json") -> dict:
    req = urllib.request.Request(api + "/v1" + path, method=method, data=body,
                                 headers={"authorization": f"Bearer {key}", "content-type": content_type})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def archive(folder: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for p in sorted(folder.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                tar.add(p, arcname=p.relative_to(folder).as_posix())
    return buf.getvalue()


def install(api: str, key: str, folder: Path) -> dict:
    boundary = uuid.uuid4().hex
    data = archive(folder)
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"package\"; filename=\"{folder.name}.tgz\"\r\n"
            f"Content-Type: application/gzip\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    return call(api, key, "POST", "/harnesses", body, f"multipart/form-data; boundary={boundary}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--admin-key-file", required=True)
    ap.add_argument("--model", default="deepseek-v4-pro", help="the model name every demo asks its provider for")
    ap.add_argument("--install", action="store_true", help="install packages/* into the organization first")
    a = ap.parse_args()
    admin = Path(a.admin_key_file).read_text().strip()
    providers = {p["api"]: p["name"] for p in call(a.api, admin, "GET", "/providers")["data"]}
    if a.install:
        for folder in sorted(p for p in (ROOT / "packages").iterdir() if (p / "harness.json").is_file()):
            print("installed", install(a.api, admin, folder)["name"])
    for app, harness in APPS.items():
        provider = providers.get(PROVIDER_FOR[harness])
        if not provider:
            sys.exit(f"the organization has no provider with the {PROVIDER_FOR[harness]} API shape, which {harness} needs")
        key = call(a.api, admin, "POST", "/keys", json.dumps({"label": app, "role": "developer", "run_only": True}).encode())
        env = ROOT / app / ".env"
        env.write_text(f"HG_API={a.api}\nHG_KEY={key['key']}\nHG_MODEL={harness}/{provider}/{a.model}\n")
        env.chmod(0o600)
        print(f"{app}: run-only key {key['hint']} ({key['id']}), model {harness}/{provider}/{a.model} -> {env.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
