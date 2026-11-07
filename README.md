# HarnessGateway demos

Three small business applications with an agent inside each, built on a
[HarnessGateway](https://github.com/HarnessGateway/harnessgateway) platform the way a customer would build them. Each is
an ordinary web app with its own SQLite database. It holds one **run-only API key**, sends **OpenAI Responses** requests
to the platform, and reads the agent's work back from the session's workspace. The agent in each is **one harness
package** built for the purpose, each on a different coding-agent CLI. The platform's own harness package builder wrote
each package from a single request.

| Demo | The application | The agent in it | On |
|---|---|---|---|
| [`crm/`](crm/) | A showroom's CRM: 75 customers on a pipeline and a map, follow-ups, an activity log, an Outbox | a sales agent that reads the whole CRM, answers with names and numbers, plans routes, and drafts emails and texts into the Outbox | [`sales-codex`](packages/sales-codex/), OpenAI Codex, over the **OpenAI** API shape |
| [`market-desk/`](market-desk/) | A commodities newsroom's desk: assignments, a release calendar, review by status | a journalist that reads the desk's primary sources and files a cited draft with charts, sources and the claims to verify | [`journalist-pi`](packages/journalist-pi/), pi, over the **Anthropic** API shape |
| [`social/`](social/) | A social media calendar: campaigns, a post per platform, a two-week calendar | a social media manager that writes each platform's post, plans the sequence, tags links and cross-links the posts | [`social-claude-code`](packages/social-claude-code/), Claude Code, over the **Anthropic** API shape |

Each app has a short recording of it in use, live: [`crm/demo.mp4`](crm/demo.mp4),
[`market-desk/demo.mp4`](market-desk/demo.mp4) and [`social/demo.mp4`](social/demo.mp4). The minutes the agent spends
working are sped up and labelled as such; nothing else is cut.

In every one, **the person decides**: the CRM sends only what someone presses Send on, the desk approves only what an
editor checked claim by claim, and the studio schedules only the posts someone approved. The agents draft.

## Running them

You need a HarnessGateway (3.1.1 or later) with a provider connected for each API shape you use, and an admin key.

```bash
git clone https://github.com/HarnessGateway/demos && cd demos
scripts/setup.py --api http://localhost:8000 --admin-key-file ~/admin.key --install --model <a model your providers serve>
python3 crm/server.py          # http://127.0.0.1:8900
python3 market-desk/server.py  # http://127.0.0.1:8910
python3 social/server.py       # http://127.0.0.1:8920
```

`setup.py` installs the three packages, creates one run-only key per app, and writes each app's `.env` (`HG_API`,
`HG_KEY`, `HG_MODEL`). The model path is `<harness>/<provider>/<model>`. The sales agent needs a provider with the
OpenAI API shape; the other two need one with the Anthropic shape.

The apps are standard-library Python servers and plain JavaScript pages, on purpose: nothing hides how the platform is
used. [`common/hg.py`](common/hg.py) is the whole client.

## How the packages were made

Each package was written by the built-in `harness-package-builder`, from the request in
[`packages/REQUESTS.md`](packages/REQUESTS.md). The builder researched the CLI, installed it in its sandbox, wrote the
package's three files and seeds (standing instructions, permission rules, hooks, settings and the output contract the
app parses), tried it where the API shape allowed, validated its output with `hgkit`, and wrote **one folder**,
`/workspace/<name>/`. That folder was imported from the session's workspace and installed. Each package installs its
CLI itself; there is no separate vanilla package of the CLI.

## What each demo shows of the platform

- **Input files.** The CRM sends its snapshot as an `input_file` with each question; the agent reads it as a file.
- **Sessions as memory.** One session per chat, per story and per campaign. A follow-up or a revision sends
  `previous_response_id`, and the agent continues in its own workspace.
- **Background turns.** The apps start a turn and poll it, showing the agent's commands as it works. A page can be
  closed and reopened while the agent works.
- **Output contracts.** Each agent ends its answer with one fenced JSON block (`crm-drafts`, `desk-report`,
  `social-plan`) that its package's instructions define and its app parses.
- **Least privilege by package.** The sales agent reaches nothing but the model. The journalist reaches only its
  primary sources. The social manager reads the web and its package refuses every social platform's API. The platform
  enforces the hosts outside the sandbox; each CLI's own rules enforce the rest inside it.
- **No keys in the apps.** The apps hold only their run-only key. The provider key is swapped in by the platform's
  door, outside the sandbox.
