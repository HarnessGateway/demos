# journalist-pi

A commodities-market desk journalist on **pi** (`@mariozechner/pi-coding-agent`), packaged for the harness. Given a
desk (biofuels or crude-oil) and an assignment, it reads the desk pack, gathers intel from the desk's primary sources
(EIA, EPA, CARB, Federal Register, USDA AMS/ERS), forms impressions, and authors a cited draft into
`/workspace/desk/<YYYY-MM-DD>/<desk>-<slug>/`. It is the drafting stage of a newsroom pipeline: it sources every
number, invents nothing, and never publishes.

## Files

- `harness.json` — manifest: pinned pi version, egress allowlists, settings, persist.
- `install` — installs the pinned pi CLI (npm) and pandas + matplotlib (venv) into `$HG_TOOLS`.
- `run` — one turn: the request becomes pi's prompt, pi's JSON-mode events become Responses events.
- `seeds/home/.pi/agent/AGENTS.md` — pi's standing instructions: the journalist role, workflow, output contract,
  non-negotiable rules.
- `seeds/home/.pi/agent/settings.json` — quiet startup, no install telemetry.
- `seeds/home/desks/{biofuels,crude-oil}/` — desk packs: `glossary.md`, `sources.md`, `style.md`, `calendar.md`.
- `tests/test_run.py` — replays recorded pi streams and checks the wire output; `tests/fixtures/` holds the records.

## Command

The platform runs `run` with `HG_REQUEST`/`HG_TOOLS`/`HG_WORKSPACE` set. `run` writes
`~/.pi/agent/models.json` each turn from the provider's base URL and model, then runs pi headless:

```
pi --mode json --provider anthropic --model <HG_MODEL> \
   --tools read,bash,edit,write,grep,find,ls \
   [--thinking <reasoning_effort>] [--append-system-prompt <instructions>] \
   [--session <saved> | --no-session] <prompt>
```

## Request → pi

| Request field | Where it goes |
| --- | --- |
| `input` text | pi's prompt, prefixed `Desk: <desk>` / `Task kind: <task>` |
| `metadata.desk` | the desk (overrides the `DESK` setting; default `biofuels`) |
| `metadata.task` | the task kind (briefing, data-release, market-wrap, explainer, news-short, research) |
| `instructions` | `--append-system-prompt` |
| `reasoning.effort` | `--thinking <level>` (off/minimal/low/medium/high/xhigh) |
| `store: false` | `--no-session` (ephemeral turn) |
| input files | written into the workspace by name, listed in the prompt as "Attached files" |
| `previous_response_id` | pi resumes its own session for the revision (see continuity) |

## pi → Responses

| pi JSON event | Responses event |
| --- | --- |
| `session` (header) | saved to state as the session id (the moment it appears) |
| `message_update` `text_delta` | `out.say` |
| `message_update` `thinking_delta` | `out.think` |
| `tool_execution_start/end` | `out.ran` (bash), `out.wrote`, `out.edited`, `out.used` (read/grep/find/ls) |
| `message_end` assistant usage | token counts on the terminal event |
| `message_end` `stopReason: error` | `out.failed` with an OpenAI code (rate_limit_exceeded / authentication_error / server_error / provider_error) |
| `message_end` `stopReason: length` | `out.stopped("max_output_tokens")` |
| `agent_end` | the terminal event is `response.completed` |

The provider token is scrubbed from every emitted string; it never reaches the client.

## Continuity (both paths)

1. **Native resume.** The pi session id is saved to state the moment pi reports it in the session header. A follow-up
   turn (a revision, e.g. "shorten the lede") passes `--session <id>`, so pi continues the same conversation and
   working tree.
2. **History fallback.** If there is no saved id, or pi answers "No session found" for a stale id, `run` starts a
   fresh pi session and hands it the conversation from `req.transcript()` to continue from. `persist` keeps
   `~/.pi/agent/sessions` across turns.

## Reach

- **install egress:** `registry.npmjs.org`, `pypi.org`, `files.pythonhosted.org` (npm + pip, as observed).
- **run egress:** `www.eia.gov`, `api.eia.gov`, `www.epa.gov`, `ww2.arb.ca.gov`, `www.federalregister.gov`,
  `www.ams.usda.gov`, `www.ers.usda.gov` — nothing else. The standing instructions forbid the agent from touching any
  other host, writing outside `/workspace`, modifying the desk packs, or running anything but `python3` and standard
  Unix tools.

## Operator settings

| Setting | Meaning | Default |
| --- | --- | --- |
| `DESK` | default desk when the request's `metadata.desk` is absent | `biofuels` |

No secrets. The provider and model come from the platform (`HG_MODEL` / `HG_PROVIDER_*`), not from settings.

## Timeouts

`run.timeout_s` is **1200** (a full gather-and-draft turn), `stop_grace_s` 10. `run` forwards SIGTERM/SIGINT to pi
and ends the turn `response.incomplete` if pi is cut short.

## Tests

`tests/test_run.py` runs `run` against recorded pi streams (`JOURNALIST_PI_REPLAY=…`) and validates every line with
the same `hgkit` check the platform uses. Fixtures cover a plain text turn, a tool turn, a resumed turn, a killed
turn, a provider error, and a stopped-short turn.
