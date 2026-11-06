# pi

The [pi coding agent](https://github.com/badlogic/pi-mono) (`@mariozechner/pi-coding-agent`), running
headless in the sandbox. One Responses request is one pi turn: the request's input is pi's prompt, pi talks to
the provider through the gateway, and pi's JSON event stream is mapped to Responses events.

- Pinned CLI: **0.73.1** (`npm: @mariozechner/pi-coding-agent`)
- Provider shape: **anthropic** (pi's `anthropic-messages` API, proxied by the gateway)
- Default model: **deepseek-v4-pro** (`HG_MODEL`)

## Files

| File | Purpose |
|---|---|
| `harness.json` | Manifest: provider, default model, egress, persist, timeouts. |
| `install` | `npm install @mariozechner/pi-coding-agent@<version>` into `$HG_TOOLS`, then verifies `pi --version`. |
| `run` | One turn: request → pi command → map pi's JSON stream → Responses events. |
| `seeds/home/.pi/agent/models.json` | Minimum config pi needs headless: the `anthropic` provider (gateway base URL) and the `deepseek-v4-pro` model. `run` rewrites this each turn from the provider env. |
| `seeds/home/.pi/agent/settings.json` | Telemetry off, provider retries off. |
| `tests/` | Recorded pi output as fixtures + `test_run.py` (see Tests). |

## The command

`install` runs once per digest: `npm install --prefix "$HG_TOOLS" "@mariozechner/pi-coding-agent@$VER"`.

`run` (per turn) launches:

```
pi --offline --mode json -p \
   --provider anthropic --model <HG_MODEL> --api-key <HG_PROVIDER_TOKEN> \
   [--append-system-prompt <instructions>] [--thinking <effort>] [--session <path>] \
   <prompt>
```

`--offline` (plus `PI_SKIP_VERSION_CHECK=1`, `PI_OFFLINE=1`) disables all of pi's startup network: update
checks, package checks, install telemetry. pi's stdin is `/dev/null` so it never reads the request JSON as a
piped prompt; the prompt is passed as an argument.

## Request fields

| Field | Where it goes |
|---|---|
| `input` (user text) | pi's prompt (argument). Input files are written into the workspace and named in the prompt. |
| `instructions` + system/developer messages | `--append-system-prompt` |
| `reasoning.effort` | `--thinking` (`none`/`off` → `off`, else passed through) |
| `metadata` | not used by pi (vanilla) |
| `store: false` | `--no-session` (ephemeral turn) |

Ignored (reported in `metadata.hg_ignored_fields`): `temperature`, `top_p`, `max_output_tokens`,
`max_tool_calls`, `text` (structured output), `tools`. pi exposes none of these per turn.

## Output mapping

`run` reads pi's `--mode json` lines and maps them:

| pi event | Responses event |
|---|---|
| `session` | saved to `req.state` immediately; a log line |
| `message_update` `text_delta` | `response.output_text.delta` (streamed into a message item) |
| `message_update` `thinking_delta` | `response.reasoning_summary_text.delta` (reasoning item) |
| `tool_execution_start` / `_end` `bash` | `shell_call` + `shell_call_output` |
| `tool_execution_start` / `_end` `write` | `apply_patch_call` (`create_file`) + output |
| `tool_execution_start` / `_end` `edit` | `apply_patch_call` (`update_file`) + output |
| other tools (`read`, `grep`, `find`, `ls`) | `function_call` + `function_call_output` |
| `agent_end` | turn is complete; usage summed from the assistant messages |
| an assistant message with `stopReason: "error"` | `response.failed` with the error (401→`authentication_error`, 429→`rate_limit_exceeded`, …) |
| non-zero exit / empty output | `response.failed` |

Raw pi lines are logged with `out.log`, never sent to the client. Exactly one terminal event is emitted, last.

## Continuity

Two paths, both required:

1. **pi's own session.** The session UUID arrives in the first JSON line; `run` saves it to `req.state` that
   instant (so a killed turn still records it). The next turn finds the session file under
   `~/.pi/agent/sessions/**/<uuid>.jsonl` (persisted via `persist`) and resumes with `--session <path>`.
2. **The history.** When there is no saved id, or the session file is gone, `run` starts a fresh pi session and
   prepends `req.transcript()` of the earlier conversation so the new session continues it.

## Known limits

- pi exposes no per-turn `temperature`/`top_p`/`max_output_tokens`/structured-output knobs; those fields are
  ignored, not honoured.
- pi's tool output is mapped for its built-in tools (`bash`, `write`, `edit`, `read`, `grep`, `find`, `ls`);
  anything else is reported as a generic `function_call`.
- The edit diff is a plain old/new concatenation, not a true unified diff.

## Tests

`python3 tests/test_run.py` runs `run` against the recorded pi fixtures (replayed by a stub `pi` in a scratch
`$HG_TOOLS`, no network) and checks every line with `hgkit.check`. Covers: a text turn, a bash tool turn, a
resumed turn (`--session` passed), a turn resumed after a kill, a provider auth error, a crashed turn
(stderr 429), a turn killed mid-way, and a SIGTERM to `run` itself (must still emit a terminal event with the
session id already saved).
