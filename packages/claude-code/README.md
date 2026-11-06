# claude-code

A harness package for **Claude Code** (`@anthropic-ai/claude-code`, pinned to `2.1.318`): the CLI as Anthropic ships
it, run headless in the sandbox — one turn is one `claude --print --output-format stream-json` invocation against the
session's provider, mapped onto the Responses stream. This is the *vanilla* base: no standing instructions, no
permission rules, no hooks. Tailor it (a purpose, a fence, operator settings) by making a copy under a new name —
`social-claude-code` is one such copy, delivered beside it.

## Files

| File | Role |
|---|---|
| `harness.json` | manifest: version `2.1.318-1`, provider `anthropic`, `defaults.model` `deepseek-v4-pro` (the model this provider serves, `HG_MODEL`), install egress `registry.npmjs.org`, run egress `*` (the public web the CLI's WebFetch/WebSearch tools reach; the door always refuses private addresses), `persist` `[".claude/projects"]` (Claude Code's session store) |
| `install` | `npm install -g --prefix "$HG_TOOLS" --allow-scripts=@anthropic-ai/claude-code @anthropic-ai/claude-code@<version>`; the postinstall copies the platform-native binary over the placeholder |
| `run` | one turn (Python + hgkit): builds the command, streams the CLI's stdout as Responses events, keeps the session id |
| `README.md`, `tests/` | this file; recorded fixtures and `test_run.py` |

## The command

```
claude -p "<input text>" --output-format stream-json --verbose --include-partial-messages \
  --system-prompt-snapshot off --dangerously-skip-permissions --model "$HG_MODEL" \
  [--append-system-prompt "<instructions>"] [--effort <level>] [--json-schema <schema>] \
  [--resume <saved session id>] [--no-session-persistence]
```

run in the workspace, with `ANTHROPIC_BASE_URL=$HG_PROVIDER_URL` (the door, no `/v1`), `ANTHROPIC_API_KEY` /
`ANTHROPIC_AUTH_TOKEN=$HG_PROVIDER_TOKEN`, and every model alias Claude Code can pick
(`ANTHROPIC_DEFAULT_*_MODEL`, `ANTHROPIC_SMALL_FAST_MODEL`, `CLAUDE_CODE_*_MODEL`) pinned to `$HG_MODEL`, so nothing
leaves for a vendor-default model the provider does not serve. Telemetry, update checks, error reporting and the bug
command are switched off (`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`, `DISABLE_TELEMETRY=1`, `DISABLE_AUTOUPDATER=1`,
`DISABLE_ERROR_REPORTING=1`, `DISABLE_BUG_COMMAND=1`). `--dangerously-skip-permissions` is what makes it headless (there
is no one to approve a prompt); a tailored copy adds the deny list and hooks that are the real fence.

## Request fields

| Request field | Where it goes |
|---|---|
| `input` (string, or the user messages' `input_text`) | the positional prompt; files are placed into the workspace and their names appended to the prompt |
| `instructions`; `system`/`developer` messages in `input` | `--append-system-prompt` |
| `previous_response_id` | the platform has already picked the session; `run` resumes Claude Code with the session id it saved in `$HG_STATE` (see Continuity) |
| `model` | `--model` and every `*_MODEL` env alias |
| `reasoning.effort` | `--effort` |
| `text.format` (`json_schema`) | `--json-schema` |
| `store: false` | `--no-session-persistence` |

Ignored, and named in `metadata.hg_ignored_fields`: `temperature`, `top_p`, `max_output_tokens`, `max_tool_calls`
(Claude Code has no flag for these), and `store` when `false`.

## Output mapping

Claude Code's `stream-json` is mapped line by line (`--verbose` is required for stream-json):

| Claude Code | Responses |
|---|---|
| `system` `init` | nothing sent to the client; its `session_id` is saved to `$HG_STATE` the moment it appears |
| `system` `thinking_tokens` / `task_*` / `status` / `stream_event` | log lines (`out.log`) |
| `assistant` message `thinking` part | `reasoning` item (`out.think`), streamed, partials de-duplicated |
| `assistant` message `text` part | assistant `message` (`out.say`), streamed, partials de-duplicated |
| `assistant` message `tool_use` (`Bash`) | `shell_call`; its `tool_result` becomes the `shell_call_output` (`out.ran`) |
| `assistant` message `tool_use` (`Write` / `Edit`) | `apply_patch_call` + output (`out.wrote` / `out.edited`), `ok` from the tool result |
| any other `tool_use` (`Read`, `WebFetch`, `WebSearch`, `Task`, `Skill`, …) | `function_call` + output (`out.used`) |
| `result` with `is_error: false` | `response.completed` with usage (`input` = input + cache-read + cache-creation tokens; `cached`, `cache_write`, `reasoning` from the result's usage) |
| `result` with `is_error: true` | `response.failed`; `api_error_status` 401→`invalid_api_key`, 429→`rate_limit_exceeded`, 5xx→`server_error`, 400→`invalid_prompt`, else `cli_error` |
| `result` with `stop_reason: max_tokens` | `response.incomplete` (`max_output_tokens`) |
| no `result` (the CLI was killed or crashed) | `response.failed` (`interrupted` on SIGTERM/SIGINT, else `cli_error`) |

Exactly one terminal event, always last.

## Continuity

Two paths, both implemented and tested:

1. **The CLI's own session.** Claude Code keeps sessions under `~/.claude/projects/` (persisted). `run` saves the
   session id to `$HG_STATE` the moment the `init` line reports it — so even a turn killed mid-way can resume — and
   the next turn runs `--resume <id>`.
2. **The history.** When there is no saved id, or Claude Code refuses it (`No conversation found`), `run` starts a
   fresh session and gives it `req.transcript()` (every earlier turn's text, commands and files) as context. A fork
   onto this harness from another arrives this way.

## Known limits

- `--dangerously-skip-permissions` auto-approves every tool call the CLI has; this base package has no deny list or
  hooks. It is the raw CLI — tailor it before an organization runs it.
- Run egress is `*` (the public web, private addresses refused by the door) so the shipped `WebFetch`/`WebSearch`
  tools work as they do out of the box.
- `[claude-code:unrecognized_model]` appears on stderr when the model name is not a Claude Code alias; it is a warning,
  not an error — the model is still used, and the line is logged, not emitted.

## Tests

`python3 tests/test_run.py` runs `run` against a stub `claude` that replays recorded fixtures (a text turn, a tool
turn, a provider error, a killed turn with no result, a resume, a history fallback, and a stale-resume fallback) and
checks every mapped line with `hgkit.check`, the validator the platform runs. Recorded output is in `tests/fixtures/`.
On the platform: install the package and send a turn; **Observability → Sessions** shows every mapped event, the CLI's
stderr tail, exit code, provider calls and door connections.
