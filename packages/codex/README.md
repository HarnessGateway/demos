# codex

OpenAI's [Codex CLI](https://github.com/openai/codex) (`@openai/codex`), pinned to **0.167.0**, headless in the
sandbox, speaking the OpenAI Responses API to the organization's OpenAI-compatible provider. This is the **vanilla**
base: no standing instructions, no hooks, no MCP, no settings. A tailored agent copies this package and adds its own
`seeds/home`, hooks and manifest fields.

## Files

| File | Role |
|---|---|
| `harness.json` | the manifest: version `0.167.0-1`, provider `openai`, `defaults.model`, install/run egress and timeouts, `persist: [".codex"]` (Codex's session store) |
| `install` | `npm install -g --prefix "$HG_TOOLS" @openai/codex@<version>` from the manifest |
| `run` | one turn: the request becomes a headless `codex exec --json`, and each JSONL event becomes a Responses event |
| `seeds/home/.codex/config.toml` | Codex's config, with `__MODEL__`/`__BASE_URL__` placeholders `run` rewrites each turn |
| `tests/` | the package test harness (`fake_codex` + `test_run.py`) and recorded fixtures |

## The command

```
codex exec --json --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check [-|resume <thread_id> -]
```

`run` writes `~/.codex/config.toml` from the template (base URL `HG_PROVIDER_URL/v1`, model `HG_MODEL`, provider
`deepseek-openai` with `wire_api = "responses"`, `approval_policy = "never"`), then executes the CLI in the workspace
with the prompt on stdin. The two flags beyond `--json` are Codex's documented mode for an externally-sandboxed
environment: Codex's own sandbox (bubblewrap) cannot create namespaces under the platform's gVisor sandbox, and
`approval_policy = "never"` covers the interactive path, so a turn never waits for a person.

## Request fields

| Request field | Where it goes |
|---|---|
| `input` text | the prompt, after the instructions and any history |
| `instructions` (and system/developer messages) | prefixed to the prompt under `Instructions:` |
| input files | written into the workspace by `req.place_inputs()` and named in the prompt |
| `HG_MODEL` | `model` in `config.toml` |
| `HG_PROVIDER_URL` / `HG_PROVIDER_TOKEN` | `base_url` / `env_key` in the provider block (no key is ever written to a file) |
| `previous_response_id` | Codex's own thread id, kept in `req.state["session"]` |

## Output mapping

| Codex JSONL | Responses |
|---|---|
| `item.completed` `agent_message` | an assistant `message`: `out.say(...)` (streamed) |
| `item.completed` `reasoning` | `out.think(...)` |
| `item.completed` `command_execution` | `out.ran(command, stdout=aggregated_output, exit=exit_code)` |
| `item.completed` `file_change` | `out.wrote` / `out.edited` / `out.deleted` |
| `item.completed` `mcp_call` | `out.called(server, tool, args)` |
| `item.completed` `web_search` | `out.item(...)` |
| `turn.completed` `usage` | the terminal `response.completed` usage: `out.done(input=…, output=…, cached=…, cache_write=…, reasoning=…)` |
| `turn.failed` | `response.failed`, code `server_error` |
| every raw line | a log line (`out.log`) |

Files the agent created, changed or deleted that Codex did not report as `file_change` items are caught by a
workspace before/after snapshot and reported as `apply_patch` items. Exactly one terminal event ends the turn.

## Continuity

1. **Codex's own session.** The thread id from the first `thread.started` event is saved to `req.state["session"]`
   the moment it appears; the next turn resumes it with `codex exec resume <id> -`.
2. **The history.** When there is no saved id, or the CLI refuses it (no thread started, non-zero exit), a fresh
   `codex exec` runs with `req.transcript()` (the session's earlier turns) prepended to the prompt.

`persist: [".codex"]` keeps the session store across turns so path 1 works.

## Known limits

- `wire_api = "responses"` is the only value Codex 0.167.0 accepts; the gateway relays `/v1/responses`, so a
  provider that is only chat-compatible (Anthropic-style) will not work.
- Codex's own sandbox is bypassed (`--dangerously-bypass-approvals-and-sandbox`) because bubblewrap cannot run under
  the platform's gVisor sandbox; the platform's sandbox is the isolation boundary.
- `web_search` is advertised by Codex but its search backend is the provider's `/alpha/search`, which the gateway
  does not relay; a tailored agent that must browse the public web should use `curl`.
- A non-zero exit with no `turn.failed` event is reported as `response.failed` (`codex exited N`).

## Tests

```
python3 tests/test_run.py
```

runs `run` against recorded `codex exec --json` fixtures (a plain text turn, a shell-command turn, the resume path,
the resume-refused fallback to history, a provider 401, a timeout, a workspace-file diff, and the prompt composition)
and validates each turn's stdout with `hgkit.check`, the reader the platform itself uses.
