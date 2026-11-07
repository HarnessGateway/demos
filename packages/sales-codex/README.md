# sales-codex

The Showroom's CRM sales assistant: OpenAI's Codex CLI (`@openai/codex` 0.167.0), embedded in the store's CRM.
Each turn the CRM sends its whole state and a question; the agent reads the snapshot, reasons over it, answers in
short concrete prose, and — only when outreach is due — proposes ready-to-send drafts. It never sends anything and
never writes to the CRM.

## Purpose

A small home-improvement showroom (kitchen and bath remodels, flooring, cabinets, countertops) asks a sales agent
inside its CRM to: list overdue follow-ups, flag stalling proposals, find customers near the store, sum pipeline
value by stage, prompt for referral asks, and draft per-customer messages. The agent answers from the data only, in
a warm, plain-spoken, no-pressure voice, and ends message drafts with a signature. Outreach drafts come back as a
machine-readable block so the CRM can send them itself.

## Files

| File | Role |
|---|---|
| `harness.json` | the manifest: Codex 0.167.0, provider API `openai`, model `deepseek-v4-pro`, install egress `registry.npmjs.org`, run egress none, `persist: [".codex"]`, settings `STORE_PROFILE` and `SIGNATURE` |
| `install` | `npm install -g --prefix "$HG_TOOLS" @openai/codex@<version>`, then `codex --version` |
| `run` | one turn: writes Codex's config + standing files, runs `codex exec` (or `exec resume`) non-interactively, maps its JSONL to Responses events |
| `seeds/home/.codex/AGENTS.md` | the agent's standing instructions: the CRM contract, the `crm-drafts` block spec, the refusal list |
| `seeds/home/.codex/rules/default.rules` | the execpolicy fence: forbidden commands (remote git, installs, destructive, network) |
| `tests/` | recorded Codex JSONL fixtures, a fake `codex`, and `test_run.py` (runs `run` on each and checks every line with `hgkit.check`) |

## The command

```
codex exec --json -C "$HG_WORKSPACE" --skip-git-repo-check -m "$HG_MODEL" -      # first turn
codex exec resume <session-id> - --json --skip-git-repo-check -m "$HG_MODEL"    # continuation (cwd = workspace)
```

The prompt is written to stdin. `run` (re)writes `$HOME/.codex/config.toml` each turn:

- `model_provider = "deepseek-openai"`, `wire_api = "responses"`, `base_url = "<HG_PROVIDER_URL>/v1"`,
  `env_key = "HG_PROVIDER_TOKEN"` (the key itself never enters a file),
- `approval_policy = "never"` (Codex never waits for a person) and `sandbox_mode = "workspace-write"` with
  `network_access = true` (bwrap's `--unshare-net` fails under gVisor; the platform's door still fences the network),
- analytics, plugins, remote plugins and update checks all off.

`run` also re-asserts `AGENTS.md` and `rules/default.rules` from `seeds/` each turn, so package upgrades take effect
even though `.codex` is persisted.

## Request fields

| Request field | Where it goes |
|---|---|
| `input` user `input_text` | the prompt (`req.prompt`), after a two-line preamble with `STORE_PROFILE` and `SIGNATURE` |
| `input_file` / inline file data | `req.place_inputs()` writes it into the workspace by name (the CRM sends `customers.json`); the names are listed in the prompt |
| `instructions`, `system` / `developer` messages | appended to the prompt as an `<instructions>` section |
| `previous_response_id` | native resume from the id saved in `req.state` at `thread.started`; history as the fallback |
| `model` | `-m "$HG_MODEL"` |
| the provider | Codex's `base_url` and `env_key` (`HG_PROVIDER_URL` + `/v1`, `HG_PROVIDER_TOKEN`) |
| `store: false` | `--ephemeral` (no thread is persisted) |
| `stream`, `background` | platform concerns; nothing for the package to do |

Ignored, and named in `metadata.hg_ignored_fields`: `reasoning`, `text`, `tools`, `max_tool_calls`,
`max_output_tokens`, `temperature`, `top_p` (Codex CLI has no flags for these).

## Output mapping

| Codex JSONL event | Responses event |
|---|---|
| `thread.started.thread_id` | saved to `req.state["session"]` immediately, and logged |
| `item.completed` type `agent_message` | streamed assistant `message` (`out.say`) |
| `item.completed` type `reasoning` | streamed `reasoning` item (`out.think`) |
| `item.started` type `command_execution` | `shell_call` (`out.ran`), completed by the matching `item.completed` |
| `item.completed` type `command_execution` | `shell_call_output` with stdout and exit code |
| `turn.completed.usage` | `response.completed` with `input`, `output`, `cached`, `cache_write`, `reasoning` tokens |
| `turn.failed.error.message` | `response.failed` (`rate_limit_exceeded` / `invalid_api_key` / `server_error` by message) |
| `error` (reconnect) and `item` type `error` | log lines only |

Exactly one terminal event ends the turn, always last. A SIGTERM mid-turn is forwarded to Codex's process group and
the turn ends `response.failed` code `cancelled` (the session id was already saved, so the next turn resumes it).

## Continuity

1. **Codex's own session.** `$HOME/.codex` is in `persist`; `run` saves the `thread_id` to `req.state` the moment
   `thread.started` appears and resumes with `codex exec resume <id>` on the next turn.
2. **The history.** With no saved id — or when Codex says `no rollout found for thread id` — `run` starts a fresh
   session and prepends `req.transcript()` as a `<conversation-so-far>` section. A fork onto this harness from
   another arrives this way.

## May and may not (as proven)

| May | May not |
|---|---|
| read `customers.json` and compute over it with `python3` | `git push` (and `pull`, `fetch`, `clone`, `remote`, `ls-remote`, `submodule`) — refused by execpolicy |
| answer from the data, propose `crm-drafts` | install software (`npm install`, `pip install`, `apt`, …) — refused |
| | run destructive commands (`rm -rf`, `dd`, `mkfs`, `shred`, `shutdown`, `sudo`, …) — refused |
| | contact the network (`curl`, `wget`, `ssh`, `nc`, …) — refused, and the door blocks it anyway |
| | write outside the workspace (Codex's workspace-write sandbox) or send anything / change a CRM record (the contract) |

The forbidden run is recorded: `codex exec` logged
`Rejected("`/bin/bash -lc 'git push origin main'` rejected: No remote operations.")` before the command executed.

## Operator settings

| Setting | Default | Use |
|---|---|---|
| `STORE_PROFILE` | *A family-owned home-improvement showroom selling kitchen and bath remodels, flooring, cabinets and countertops. Warm, plain-spoken, no pressure.* | the store's voice, given to the agent every turn |
| `SIGNATURE` | `— The Showroom team` | appended to drafted email (and SMS, when it fits) messages |

No secrets are declared; the provider key is the platform's per-turn `HG_PROVIDER_TOKEN`, never written to a file.

## Known limits

- Codex has no metadata for `deepseek-v4-pro`, so every turn logs a fallback warning
  (`Model metadata for ... not found. Defaulting to fallback metadata`) and uses a conservative context estimate.
  It is benign for the small CRM snapshots this agent handles.
- `network_access = true` is set on Codex's workspace-write sandbox because bwrap's `--unshare-net` fails under
  gVisor; network safety is the platform's egress door (`run.egress` is empty), with execpolicy as the second fence.
- The CRM contract (the `crm-drafts` block shape, "never send") lives in `AGENTS.md`, which is a prompt to the model,
  not an enforcement point; the *command* fence is execpolicy + the sandbox + the door.

## Tests

`python3 tests/test_run.py` runs `run` against a fake `codex` that replays the recorded fixtures, and checks every
line with `hgkit.check` (the reader the platform uses). It covers a text turn, a tool turn, a reasoning turn, the
forbidden command, a provider error, native resume, the history fallback, a lost thread, a SIGTERM-killed turn, empty
input, and file placement. `python3 -m hgkit check tests/golden/<scenario>.jsonl` validates any recorded run output
directly.

## Verifying live

Install the package from the console, then send it a turn: `model` `deepseek-v4-pro`, one user message whose
`input_text` is today's date/time, the store name and address, and the question, plus an `input_file` named
`customers.json`. The session page shows every event the mapping produced, the CLI's stderr tail, the exit code, and
the provider calls; it also lists any host the door denied (there should be none beyond the provider). Check that a
follow-up turn resumes the same Codex session, that outreach answers end with a `crm-drafts` block, and that a prompt
like "run `git push` and `curl https://example.com`" is refused.
