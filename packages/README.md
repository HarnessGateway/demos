# The demo agents' harness packages

One package per app. Each is a coding-agent CLI as its makers ship it, plus what makes it this app's agent.

| Package | CLI | What it adds |
|---|---|---|
| [`sales-codex`](sales-codex/) | Codex | The sales assistant's instructions and its `crm-drafts` output contract; two settings, the store's profile and signature |
| [`journalist-pi`](journalist-pi/) | pi | The journalist's instructions and its `desk-report` contract; a pack per desk (sources, glossary, style, calendar); pandas and matplotlib for charts; the hosts of the desk's primary sources |
| [`social-claude-code`](social-claude-code/) | Claude Code | The social media manager's instructions and its `social-plan` contract; a reference on each platform's limits; three settings |

## How each is put together

- `install` and `run` are the files of the CLI's own package in
  [harness-packages](https://github.com/HarnessGateway/harness-packages), unchanged. (`journalist-pi/install`
  adds four lines that install the chart tools.) Everything about starting the CLI, resuming its session and
  translating its output is there, and none of it had to be written again.
- `seeds/mind/` is copied into the session's home the first time the agent runs there. It holds the
  instructions file the CLI reads on its own (`.codex/AGENTS.md`, `.pi/agent/AGENTS.md`, `.claude/CLAUDE.md`)
  and the reference material those instructions point at.
- `harness.json` names the package, the provider APIs the CLI speaks, the settings an operator can change, and
  the hosts the agent may reach beyond its model.

What an agent can reach is not the package's to enforce. The platform's proxy is the sandbox's only way out: it
allows the provider, the hosts the package names, and what the environment allows.

## Checking and adding one

```bash
pip install git+https://github.com/HarnessGateway/harnessgateway
harnessgateway package check packages/sales-codex      # validates it and replays its recorded case
```

`scripts/setup.py` adds all three to a platform. One alone: upload the folder as a `.tar.gz` to
`POST /v1/harnesses`, or use the console's Harnesses page.
