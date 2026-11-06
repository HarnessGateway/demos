# HarnessGateway demos

Two agentic applications built on a [HarnessGateway](https://github.com/HarnessGateway/harnessgateway) platform, the
way a customer would build them: each is an ordinary web app that holds one **run-only API key** named after it, sends
**OpenAI Responses** requests to the platform, and reads the agent's work back from the session's workspace. The agent
in each is a **harness package** built for the purpose, each on a different coding-agent CLI (Codex and pi), written by the platform's own
harness package builder in the console chat and installed from that session's workspace.

| Demo | What it is | The agent | On |
|---|---|---|---|
| [`crm/`](crm/) | A small CRM: accounts, contacts, deals, notes, and a sales agent beside each account that researches, drafts outreach and call plans, and proposes next steps. A person approves before anything is sent. | [`packages/sales-codex`](packages/sales-codex/) | OpenAI Codex |
| [`market-desk/`](market-desk/) | A commodities newsroom desk: scheduled and ad-hoc assignments, drafts with sources and a claims-to-verify list, editor review, a research thread. | [`packages/journalist-pi`](packages/journalist-pi/) | pi |

The platform is the same for both: it runs each turn in a gVisor sandbox with the package's egress and secrets
rules, keeps the session's workspace between turns, swaps a per-turn token for the organization's provider key at the
gateway, and streams Responses events back. The apps never see a provider key, never run a CLI, and never hold more
than their own run-only key.

## Running them

You need a HarnessGateway (2.4.0 or later) with a provider connected, and an admin key. On a fresh install, `init` prints
one; the console's **Access → API keys** mints another.

```bash
git clone https://github.com/HarnessGateway/demos && cd demos
scripts/setup.py --api http://localhost:8000 --admin-key-file ~/admin.key --install --model <a model your provider serves>
python3 crm/server.py          # http://127.0.0.1:8900
python3 market-desk/server.py  # http://127.0.0.1:8910
```

`setup.py` installs the two packages (and the vanilla CLI packages they were built on), creates one run-only key per
app and writes each app's `.env` (`HG_API`, `HG_KEY`, `HG_MODEL`). The model path is `<harness>/<provider>/<model>`:
the sales agent needs a provider with the OpenAI API shape, the journalist one with the Anthropic shape.

The apps are standard-library Python servers and vanilla JavaScript pages, on purpose: nothing here hides how the
platform is used. [`common/hg.py`](common/hg.py) is the whole client.

## How the packages were made

Each package was written by the built-in `harness-package-builder` in the console's chat, from a tailored request
([`packages/REQUESTS.md`](packages/REQUESTS.md)): the builder researched the CLI, installed it in its sandbox, wrote
the three files and the seeds, tried it against the organization's provider where the API shape allowed, validated its
output with `hgkit`, and wrote the package under `/workspace/<name>/`. **New harness from workspace** on that session's
page turned the folder into a draft; **Install** made it a harness. The packages here are those folders as installed.

## What each demo shows of the platform

- **Sessions as the unit of memory.** One session per account, per engagement, per research thread: the workspace and
  the CLI's own memory carry from turn to turn, and `previous_response_id` is all the app sends.
- **Background turns.** The apps start a turn and poll; a page can be closed and reopened while the agent works.
- **Attribution.** Every request carries the person (`user`): the console's Sessions and Usage pages show who asked,
  by app (the key) and by person.
- **The human in the loop, where it belongs.** The agent drafts; the CRM sends only what a rep approves; the desk
  publishes only what an editor checked claim by claim.
- **Least privilege by package.** Each package names the hosts its agent may reach and the tools it may use; the
  platform enforces the fence outside the sandbox, the CLI's own rules inside.
