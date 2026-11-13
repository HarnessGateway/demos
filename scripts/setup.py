#!/usr/bin/env python3
"""Point the demos at a HarnessGateway. With an admin key it adds the three demo packages, makes the environment
the social media manager runs in, creates one key per app that can only run turns, and writes each app's .env.

    scripts/setup.py --api http://localhost:8000 --admin-key-file ~/admin.key --provider deepseek [--model NAME]

The provider must already exist on the platform, with base URLs for the APIs the three agents speak: OpenAI
Responses (the sales agent, on Codex) and Anthropic Messages (the journalist, on pi, and the social media manager,
on Claude Code). Without --model each agent uses the provider's default model.

Standard library only, like the apps.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import tarfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# app: (its harness package, the provider API that harness speaks, the environment it runs in)
APPS = {
    "crm": ("sales-codex", "openai-responses", "default"),
    "market-desk": ("journalist-pi", "anthropic", "default"),
    "social": ("social-claude-code", "anthropic", "web"),
}

# The social media manager reads whatever page a campaign points at, so its sandbox reaches the public web, except
# the platforms' own APIs: it drafts, it never posts. The other two agents stay in the default environment, where
# a sandbox reaches its provider and the hosts its package names, and nothing else.
WEB = {
    "name": "web",
    "network": {"mode": "open", "deny": [
        "api.twitter.com", "api.x.com", "graph.facebook.com", "api.linkedin.com", "api.threads.net", "bsky.social"]},
}


class Platform:
    def __init__(self, api: str, key: str) -> None:
        self.api, self.key = api.rstrip("/"), key

    def call(self, method: str, path: str, body: bytes | None = None, content_type: str = "application/json") -> dict:
        request = urllib.request.Request(self.api + "/v1" + path, method=method, data=body, headers={
            "authorization": f"Bearer {self.key}", "content-type": content_type})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            sys.exit(f"{method} {path}: {error.code} {error.read().decode(errors='replace')[:500]}")

    def post(self, path: str, body: dict) -> dict:
        return self.call("POST", path, json.dumps(body).encode())

    def exists(self, path: str) -> bool:
        request = urllib.request.Request(self.api + "/v1" + path, headers={"authorization": f"Bearer {self.key}"})
        try:
            urllib.request.urlopen(request, timeout=30).close()
            return True
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return False
            raise

    def add_package(self, folder: Path) -> str:
        """Upload a package folder as the archive the platform takes, and return the harness's name."""
        packed = io.BytesIO()
        with tarfile.open(fileobj=packed, mode="w:gz") as tar:
            for path in sorted(folder.rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    tar.add(path, arcname=path.relative_to(folder).as_posix())
        boundary = uuid.uuid4().hex
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="package"; filename="{folder.name}.tar.gz"\r\n'
                f"Content-Type: application/gzip\r\n\r\n").encode() + packed.getvalue() + f"\r\n--{boundary}--\r\n".encode()
        return self.call("POST", "/harnesses", body, f"multipart/form-data; boundary={boundary}")["name"]

    def wait_for_installs(self, harness: str) -> list[dict]:
        while True:
            installs = self.call("GET", f"/harnesses/{harness}/installs")["data"]
            if installs and all(install["status"] != "pending" for install in installs):
                return installs
            time.sleep(3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--admin-key-file", required=True)
    parser.add_argument("--provider", required=True, help="the name of a provider on the platform")
    parser.add_argument("--model", default="", help="a model of that provider; its default model when left out")
    args = parser.parse_args()
    platform = Platform(args.api, Path(args.admin_key_file).expanduser().read_text().strip())

    provider = platform.call("GET", f"/providers/{args.provider}")
    for app, (harness, api, _) in APPS.items():
        if api not in provider["apis"]:
            sys.exit(f"the provider {args.provider} has no base URL for the {api} API, which {harness} ({app}) needs")

    if not platform.exists("/environments/web"):
        platform.post("/environments", WEB)
        print("environment web: the public web, without the social platforms' APIs")

    for app, (harness, _, environment) in APPS.items():
        platform.add_package(ROOT / "packages" / harness)
        if environment != "default":
            platform.post(f"/harnesses/{harness}/install", {"environment": environment})
        print(f"{harness}: added, installing ...", flush=True)
    for harness, _, _ in APPS.values():
        failed = [install for install in platform.wait_for_installs(harness) if install["status"] != "ready"]
        if failed:
            sys.exit(f"{harness} did not install:\n{failed[0]['log'][-2000:]}")
        print(f"{harness}: installed")

    for app, (harness, _, environment) in APPS.items():
        key = platform.post("/keys", {"name": f"demo-{app}", "role": "runner"})
        place = "" if environment == "default" else f"{environment}:"
        model = f"{place}{harness}/{args.provider}" + (f"/{args.model}" if args.model else "")
        env = ROOT / app / ".env"
        env.write_text(f"HG_API={args.api}\nHG_KEY={key['key']}\nHG_MODEL={model}\n")
        env.chmod(0o600)
        print(f"{app}: key {key['id']} (runs turns, nothing else), model {model} -> {env.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
