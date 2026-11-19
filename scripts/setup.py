#!/usr/bin/env python3
"""Point the demos at a HarnessGateway. With an admin key it adds the three demo packages, makes the environment
each agent runs in and has it carry the agent's harness, waits for the installs, creates one key per app that can
only run turns, and writes each app's .env.

    scripts/setup.py --api http://localhost:8000 --admin-key-file ~/admin.key --provider deepseek [--model NAME]

The provider must already exist on the platform, with base URLs for the APIs the three agents speak: OpenAI
Responses (the sales agent, on Codex) and Anthropic Messages (the journalist, on pi, and the social media manager,
on Claude Code). Without --model each agent uses the first of the models the provider lists.

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
    "crm": ("sales-codex", "openai-responses", "model-only"),
    "market-desk": ("journalist-pi", "anthropic", "primary-sources"),
    "social": ("social-claude-code", "anthropic", "web"),
}

# The environment decides what an agent reaches; a package names no host. One environment per agent:
# the sales agent reaches its model and nothing else;
# the journalist reaches its model and the desks' primary sources (EIA, EPA, CARB, the Federal Register, USDA);
# the social media manager reads whatever page a campaign points at, so it reaches the public web, except the
# platforms' own APIs: it drafts, it never posts.
ENVIRONMENTS = {
    "model-only": {"network": {"mode": "closed"}},
    "primary-sources": {"network": {"mode": "limited", "package_managers": False, "allow": [
        "www.eia.gov", "api.eia.gov", "www.epa.gov", "ww2.arb.ca.gov", "www.federalregister.gov",
        "www.ams.usda.gov", "www.ers.usda.gov"]}},
    "web": {"network": {"mode": "open", "deny": [
        "api.twitter.com", "api.x.com", "graph.facebook.com", "api.linkedin.com", "api.threads.net", "bsky.social"]}},
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

    def carry(self, name: str, harnesses: list[str]) -> bool:
        """Have the environment of this name carry these harnesses besides those it carries, making it when it is
        not there, and say whether it was made. A request may name only a harness its environment carries; the
        environment installs each one it carries on its image."""
        if not self.exists(f"/environments/{name}"):
            self.post("/environments", {"name": name, **ENVIRONMENTS[name], "harnesses": sorted(harnesses)})
            return True
        carried = self.call("GET", f"/environments/{name}")["harnesses"]
        self.call("PATCH", f"/environments/{name}",
                  json.dumps({**ENVIRONMENTS[name], "harnesses": sorted({*carried, *harnesses})}).encode())
        return False

    def wait_for_installs(self, environment: str, harnesses: list[str]) -> list[dict]:
        """Each of these harnesses' installs on the environment's image, once none is waiting any more."""
        while True:
            shown = self.call("GET", f"/environments/{environment}")
            if shown["build"] and shown["build"]["status"] == "failed":
                sys.exit(f"environment {environment}: its setup failed:\n{shown['build'].get('log', '')[-2000:]}")
            installs = [install for install in shown["installs"] if install["harness"] in harnesses]
            if installs and all(install["status"] not in (None, "pending") for install in installs):
                return installs
            time.sleep(3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--admin-key-file", required=True)
    parser.add_argument("--provider", required=True, help="the name of a provider on the platform")
    parser.add_argument("--model", default="", help="a model of that provider; the first it lists when left out")
    args = parser.parse_args()
    platform = Platform(args.api, Path(args.admin_key_file).expanduser().read_text().strip())

    provider = platform.call("GET", f"/providers/{args.provider}")
    for app, (harness, api, _) in APPS.items():
        if api not in provider["apis"]:
            sys.exit(f"the provider {args.provider} has no base URL for the {api} API, which {harness} ({app}) needs")
    chosen = args.model or next(iter(provider.get("models") or []), "")
    if not chosen:
        sys.exit(f"the provider {args.provider} lists no models: name one with --model")

    for harness, _, _ in APPS.values():
        platform.add_package(ROOT / "packages" / harness)
        print(f"{harness}: added", flush=True)

    # Each environment carries the harnesses that run in it, and installs them on its image.
    carrying: dict[str, list[str]] = {}
    for harness, _, environment in APPS.values():
        carrying.setdefault(environment, []).append(harness)
    for environment, harnesses in carrying.items():
        if platform.carry(environment, harnesses):
            print(f"environment {environment}: made")
        print(f"environment {environment}: carries {', '.join(harnesses)}, installing ...", flush=True)
    for environment, harnesses in carrying.items():
        for install in platform.wait_for_installs(environment, harnesses):
            if install["status"] != "ready":
                sys.exit(f"{install['harness']} did not install in {environment}:\n{install.get('log', '')[-2000:]}")
            print(f"{install['harness']}: installed in {environment}")

    for app, (harness, _, environment) in APPS.items():
        key = platform.post("/keys", {"name": f"demo-{app}", "role": "runner"})
        model = f"{environment}/{harness}/{args.provider}/{chosen}"
        env = ROOT / app / ".env"
        env.write_text(f"HG_API={args.api}\nHG_KEY={key['key']}\nHG_MODEL={model}\n")
        env.chmod(0o600)
        print(f"{app}: key {key['id']} (runs turns, nothing else), model {model} -> {env.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
