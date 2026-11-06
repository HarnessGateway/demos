# sales-codex

An account executive's sales agent on [OpenAI's Codex CLI](https://github.com/openai/codex) (`@openai/codex`,
pinned to **0.167.0**), tailored for a CRM: one account per task, researched on the public web, written up into the
workspace as an account brief, outreach email, call plan and next steps — and answered in prose. It never sends
anything and never writes to the CRM.

It is the [`codex`](../codex) vanilla base plus the agent's standing instructions, a PreToolUse deny hook that
hard-blocks the operations it must never perform, and two operator settings.

## The agent

- **Research the company on the public web** (read-only GETs) and write an account brief.
- **Draft outreach or follow-up email** for a named contact.
- **Prepare a call plan**: questions to ask and objections to expect.
- **Summarize notes** and **propose next steps**.

The task arrives as an account record (company, website, contacts, open deals, recent notes as JSON) plus one ask in
plain language. Files go under `accounts/<slug>/`: `brief.md`, `outreach/<YYYY-MM-DD>-<topic>.md`, `call-prep.md`,
`next-steps.md`; the substance is also answered in prose.

## Files

| File | Role |
|---|---|
| `harness.json` | manifest: provider `openai`, `run.egress ["*"]` (public web), settings `SALES_PLAYBOOK` and `REGION`, `persist [".codex"]` |
| `install` | `npm install -g --prefix "$HG_TOOLS" @openai/codex@<version>` |
| `run` | one turn, as the vanilla base, plus writing `~/.codex/AGENTS.md` from the settings and enabling the deny hook |
| `seeds/home/.codex/AGENTS.md` | the agent's standing instructions, with `__SALES_PLAYBOOK__`/`__REGION__` placeholders `run` fills each turn |
| `seeds/home/.codex/config.toml` | Codex config incl. the `[[hooks.PreToolUse]]` block pointing at `hooks/deny.py` |
| `hooks/deny.py` | the PreToolUse hook: denies git remotes, sending data out, installing software, destructive commands, writes outside the workspace |
| `tests/` | `test_run.py` (turn mapping) and `test_sales.py` (hook + settings), with recorded fixtures |

## The command

```
codex exec --json --dangerously-bypass-approvals-and-sandbox --dangerously-bypass-hook-trust --skip-git-repo-check [-|resume <thread_id> -]
```

`run` writes `~/.codex/config.toml` (base URL `HG_PROVIDER_URL/v1`, model `HG_MODEL`, provider `deepseek-openai`,
`wire_api = "responses"`, the hook path) and `~/.codex/AGENTS.md` (the settings), then executes the CLI in the
workspace with the prompt on stdin. `--dangerously-bypass-approvals-and-sandbox` is Codex's mode for an
externally-sandboxed environment (its bubblewrap sandbox cannot run under the platform's gVisor sandbox);
`--dangerously-bypass-hook-trust` makes the deny hook's JSON decisions bind so the agent never waits for a person.

## Safety

The agent's "never" rules are enforced in two layers:

1. **Standing instructions** (`AGENTS.md`): never send anything, never write to the CRM, never write outside the
   workspace, never touch a git remote, never install software, public web only.
2. **The PreToolUse deny hook** (`hooks/deny.py`), the hard control: every `Bash` command the model proposes is
   checked and denied with a recorded reason when it matches a forbidden pattern. Safe commands — read-only GETs,
   file work inside the workspace, `git status`/`git log` — pass through.

The platform's sandbox (filesystem isolation, egress allowlist) is the outer boundary.

## Operator settings

| Setting | Meaning | Default |
|---|---|---|
| `SALES_PLAYBOOK` | the organization's playbook applied to every account: audience, value prop, messaging, tone | a generic B2B software vendor selling to mid-market operations teams |
| `REGION` | market region for tone, spelling and examples | `US` |

Both are declared in `harness.json` with defaults; override them per organization (or per account) in the console.
They are injected as environment variables and substituted into `AGENTS.md` at the start of every turn. No secrets.

## Request fields

| Request field | Where it goes |
|---|---|
| `input` text (the account record JSON + the ask) | the prompt, after the instructions and any history |
| `instructions` | prefixed to the prompt under `Instructions:` |
| input files | written into the workspace by `req.place_inputs()` and named in the prompt |
| `HG_MODEL` | `model` in `config.toml` |
| `HG_PROVIDER_URL` / `HG_PROVIDER_TOKEN` | `base_url` / `env_key` (no key is ever written to a file) |
| `SALES_PLAYBOOK`, `REGION` | substituted into `~/.codex/AGENTS.md` |
| `previous_response_id` | Codex's own thread id, kept in `req.state["session"]` |

## Output mapping

Identical to the vanilla [`codex`](../codex) base: `agent_message` → assistant message, `reasoning` → thinking,
`command_execution` → `out.ran`, `file_change` → `out.wrote`/`out.edited`/`out.deleted`, `turn.completed` usage →
`response.completed`, `turn.failed` → `response.failed`. Files the agent wrote that Codex did not report as
`file_change` are caught by a workspace snapshot and reported as `apply_patch` items. Exactly one terminal event.

## Continuity

1. **Codex's own session**: the thread id from `thread.started` is saved to `req.state["session"]` and resumed next
   turn with `codex exec resume <id> -`.
2. **The history**: with no saved id, or if the CLI refuses it, a fresh `codex exec` runs with `req.transcript()`
   prepended — one session per account continues across turns.

## Known limits

- `wire_api = "responses"` is the only value Codex 0.167.0 accepts; the gateway relays `/v1/responses`.
- Codex's own sandbox is bypassed (bubblewrap cannot run under gVisor); the platform sandbox is the isolation boundary.
- `web_search` is advertised but its backend (`/alpha/search`) is not relayed by the gateway, so the agent browses
  the public web with `curl` (GETs pass the deny hook).
- The deny hook is pattern-based and a backstop, not a parser; the standing instructions remain the first line of the
  "never send / never write to the CRM" rules.

## Tests

```
python3 tests/test_run.py    # the turn mapping (text, tool, resume, fallback, 401, timeout, diff, prompt)
python3 tests/test_sales.py  # the deny hook (deny/allow) and AGENTS.md/config.toml generation
```

`test_run.py` drives `run` against recorded `codex exec --json` fixtures; `test_sales.py` feeds command strings
straight through `hooks/deny.py`. Both validate `run`'s stdout with `hgkit.check`, the reader the platform uses.
